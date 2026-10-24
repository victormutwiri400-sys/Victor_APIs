#!/usr/bin/env python3
"""
migrate_images.py — Phase 2: bulk-migrate legacy local image references to Cloudinary.

Converts `photo` values stored as bare filenames in the live
`victordesigner_fullstack` database into full Cloudinary `secure_url` values.

Tables / columns handled:
    dining.dining_id  -> hotel_management/dining
    gallery.gallery_id-> hotel_management/gallery
    rooms.room_id     -> hotel_management/rooms
    users.user_id     -> hotel_management/profiles   (non-empty users.photo only)

Key behaviors
-------------
* Credentials come ONLY from environment variables (or an optional git-ignored
  `.env.migration` file). Nothing is ever printed or logged.
* Deterministic public_id derived from the original filename, so duplicates
  (e.g. `master5.jpg` on rooms 5 and 21) reuse ONE Cloudinary asset and
  interrupted re-runs do not create duplicates.
* Every value that already starts with http(s):// is skipped untouched.
* A record is updated ONLY after the source exists AND the upload succeeds AND
  the resulting Cloudinary asset verifies.
* Only the image column is updated, via parameterized SQL, by primary key.
  IDs, descriptions, prices, user data, bookings and all other columns are
  preserved.
* Nothing is deleted: no original images, no existing Cloudinary assets
  (including assets belonging to other projects).
* Default mode is DRY-RUN. Real database changes require --execute.

Example usage (Windows PowerShell):
    python migrate_images.py --dry-run
    python migrate_images.py --dry-run --table rooms
    python migrate_images.py --execute --limit 3
    python migrate_images.py --execute
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import logging
import os
import re
import sys
import time
import urllib.parse
from dataclasses import dataclass

import requests

# Cloudinary/MySQL are imported lazily inside functions so that importing this
# module (or running --help) has no side effects.

LOG = logging.getLogger("migrate_images")

# ---------------------------------------------------------------------------
# Configuration (built from the live-schema audit — do not guess)
# ---------------------------------------------------------------------------

# (table, primary-key column, image column, cloudinary folder, static subfolder)
# The static subfolder is the URL directory on the AlwaysData server:
# https://<host>/static/<static_subfolder>/<filename> (audit-verified 81/81).
@dataclass(frozen=True)
class TableConfig:
    table: str
    id_col: str
    image_col: str
    cloudinary_folder: str
    static_subfolder: str

# NOTE: `users` uses `hotel_management/profiles` (matches /api/Profile).
TABLES = (
    TableConfig("dining", "dining_id", "photo", "hotel_management/dining", "images"),
    TableConfig("gallery", "gallery_id", "photo", "hotel_management/gallery", "gallery"),
    TableConfig("rooms", "room_id", "photo", "hotel_management/rooms", "rooms"),
    TableConfig("users", "user_id", "photo", "hotel_management/profiles", "profiles"),
)

#: Default origin of the legacy images (audit-verified reachable).
DEFAULT_STATIC_BASE_URL = "https://victordesigner.alwaysdata.net/static"

#: Optional git-ignored credentials file, resolved relative to THIS script so
#: the script works from any working directory.
MIGRATION_ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env.migration")

#: Values that are considered "already migrated / absolute" — never touched.
ABSOLUTE_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def load_env_file(path):
    """Minimal .env loader (no external dependency). Env vars win over file."""
    if not path or not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):].strip()
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def get_required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(
            f"Missing required environment variable '{name}'. "
            "Set it or add it to .env.migration (see .env.migration.example)."
        )
    return value


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sanitize_public_id(filename):
    """Deterministic, URL-safe public_id from a legacy filename.

    Examples:
        'download (1).jpeg' -> 'download-1'
        'master5.jpg'       -> 'master5'
        'control room.jpg'  -> 'control-room'
    """
    stem = os.path.splitext(os.path.basename(filename))[0]
    value = stem.strip().lower()
    value = re.sub(r"[^a-z0-9._-]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    if value:
        return value
    # Degenerate names (e.g. '....jpg') -> content-derived fallback so
    # different degenerate files never share one public_id.
    return "image-" + sha256_bytes(filename.encode("utf-8"))[:8]


# ---------------------------------------------------------------------------
# Database access (read + single-column update, parameterized)
# ---------------------------------------------------------------------------

def connect_mysql():
    import pymysql.cursors  # lazy import

    return pymysql.connect(
        host=os.environ.get("MYSQL_HOST", "mysql-victordesigner.alwaysdata.net"),
        user=os.environ.get("MYSQL_USER", "victordesigner"),
        password=get_required("MYSQL_PASSWORD"),
        database=os.environ.get("MYSQL_DATABASE", "victordesigner_fullstack"),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
        connect_timeout=15,
        read_timeout=120,
        write_timeout=60,
    )


def fetch_image_rows(conn, cfg):
    """Return [(pk, photo), ...] for rows whose image column is non-blank."""
    sql = (
        f"SELECT `{cfg.id_col}`, `{cfg.image_col}` FROM `{cfg.table}` "
        f"WHERE `{cfg.image_col}` IS NOT NULL AND `{cfg.image_col}` <> '' "
        f"ORDER BY `{cfg.id_col}`"
    )
    with conn.cursor() as cur:
        cur.execute(sql)
        return [(row[cfg.id_col], (row[cfg.image_col] or "").strip()) for row in cur.fetchall()]


def update_image_url(conn, cfg, pk, new_url):
    """Update only the image column for the exact primary key. Parameterized."""
    sql = f"UPDATE `{cfg.table}` SET `{cfg.image_col}` = %s WHERE `{cfg.id_col}` = %s"
    with conn.cursor() as cur:
        return cur.execute(sql, (new_url, pk))


# ---------------------------------------------------------------------------
# Source resolution & download (spaces, parentheses, URL-encoding, retries)
# ---------------------------------------------------------------------------

def _local_source_path(source_dir, cfg, filename):
    if not source_dir:
        return None
    candidate = os.path.join(source_dir, cfg.static_subfolder, filename)
    if os.path.isfile(candidate) and os.path.getsize(candidate) > 0:
        return candidate
    return None


def source_url_for(cfg, filename, static_base):
    encoded = urllib.parse.quote(filename, safe="")  # handles spaces/parens/UTF-8
    return f"{static_base}/{cfg.static_subfolder}/{encoded}"


def download_source(cfg, filename, static_base, source_dir, retries, timeout=30):
    """Return (data_bytes, source_kind, source_ref). Raises on final failure."""
    local = _local_source_path(source_dir, cfg, filename)
    if local:
        with open(local, "rb") as handle:
            data = handle.read()
        if not data:
            raise RuntimeError(f"local source is empty: {local}")
        return data, "local_file", local

    url = source_url_for(cfg, filename, static_base)
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, timeout=timeout, stream=True)
            resp.raise_for_status()
            content_type = (resp.headers.get("Content-Type") or "").lower()
            if content_type and not content_type.startswith("image/"):
                # Some servers report application/octet-stream for .avif/.jfif.
                if content_type not in ("application/octet-stream", "binary/octet-stream"):
                    LOG.warning("Unexpected Content-Type for %s: %s", url, content_type)
            data = resp.content
            if not data:
                raise RuntimeError("empty body")
            return data, "http_url", url
        except Exception as exc:  # noqa: BLE001 - retries must be broad
            last_error = exc
            LOG.warning("download attempt %d/%d failed for %s: %s",
                        attempt, retries, url, exc)
            if attempt < retries:
                time.sleep(2 ** attempt)  # 2s, 4s, 8s backoff
    raise RuntimeError(f"download failed after {retries} attempts: {last_error}")


# ---------------------------------------------------------------------------
# Cloudinary upload / reuse / verify
# ---------------------------------------------------------------------------

def configure_cloudinary():
    import cloudinary

    cloudinary.config(
        cloud_name=get_required("CLOUDINARY_CLOUD_NAME"),
        api_key=get_required("CLOUDINARY_API_KEY"),
        api_secret=get_required("CLOUDINARY_API_SECRET"),
        secure=True,
    )


def _resource_exists(public_id):
    """True if the Cloudinary asset already exists (read-only)."""
    import cloudinary.api  # lazy import

    try:
        cloudinary.api.resource(public_id, resource_type="image")
        return True
    except Exception:  # noqa: BLE001 - an absent asset surfaces as an error
        return False


def get_cloudinary_url(public_id):
    """Read the secure_url of an existing asset (for the reuse path)."""
    import cloudinary.api

    info = cloudinary.api.resource(public_id, resource_type="image")
    url = info.get("secure_url") or info.get("url")
    if not url:
        raise RuntimeError(f"existing asset {public_id} has no secure_url")
    return url


def upload_or_reuse(data, public_id, retries):
    """Upload (or reuse) image bytes. Returns (secure_url, action).

    `public_id` MUST be the full public id including the folder path
    (e.g. 'hotel_management/rooms/master5'), so lookups, verification and the
    final asset path are unambiguous.
    """
    import cloudinary.uploader  # lazy import

    # 1) Reuse if the deterministic public_id already exists in Cloudinary.
    try:
        if _resource_exists(public_id):
            url = get_cloudinary_url(public_id)
            return url, "reused_existing_asset"
    except Exception as exc:  # noqa: BLE001
        LOG.warning("asset check failed for %s (%s); will attempt a real upload",
                    public_id, exc)

    # 2) Upload with a deterministic public_id — no auto-suffix, no overwrite.
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            result = cloudinary.uploader.upload(
                io.BytesIO(data),
                public_id=public_id,
                resource_type="image",
                overwrite=False,
                unique_filename=False,
                use_filename=False,
            )
            return result["secure_url"], "uploaded"
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            LOG.warning("upload attempt %d/%d failed for %s: %s",
                        attempt, retries, public_id, exc)
            # A concurrent run may have created it — re-check before retrying.
            try:
                if _resource_exists(public_id):
                    url = get_cloudinary_url(public_id)
                    return url, "reused_existing_asset"
            except Exception:  # noqa: BLE001
                pass
            if attempt < retries:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"upload failed after {retries} attempts: {last_error}")


def verify_asset(public_id, secure_url, do_http=True):
    """Verify the Cloudinary asset with public_id `public_id` actually serves
    the EXACT `secure_url` we intend to write. Raises on any mismatch."""
    import cloudinary.api

    try:
        info = cloudinary.api.resource(public_id, resource_type="image")
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"asset not found on Cloudinary for {public_id}: {exc}")
    expected = info.get("secure_url") or info.get("url")
    if not expected:
        raise RuntimeError(f"asset {public_id} has no usable URL on Cloudinary")
    if expected != secure_url:
        raise RuntimeError(f"URL mismatch for {public_id}: Cloudinary reports "
                           f"{expected}, candidate is {secure_url}")
    if do_http:
        resp = requests.get(secure_url, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code} on {secure_url}")
        if not resp.content:
            raise RuntimeError(f"empty response on {secure_url}")
    return "verified"


# ---------------------------------------------------------------------------
# CSV manifest / rollback writers
# ---------------------------------------------------------------------------

MANIFEST_FIELDS = [
    "migrated_at", "mode", "table", "id_column", "pk", "image_column",
    "old_value", "source_kind", "source_url_or_path", "source_size_bytes",
    "source_sha256", "public_id", "cloudinary_url", "status", "detail", "retries",
]
ROLLBACK_FIELDS = [
    "migrated_at", "mode", "table", "id_column", "pk", "image_column",
    "old_value", "new_value", "status",
]


def open_csv(path, fields):
    handle = open(path, "w", newline="", encoding="utf-8-sig")
    writer = csv.DictWriter(handle, fieldnames=fields)
    writer.writeheader()
    return handle, writer


# ---------------------------------------------------------------------------
# Core migration routine
# ---------------------------------------------------------------------------

class _StopProcessing(Exception):
    """Internal signal to stop early (e.g. after --limit rows)."""


def run_migration(args):
    mode = "execute" if args.execute else "dry_run"

    # --- Safe defaults + validation --------------------------------------
    table_names = {cfg.table: cfg for cfg in TABLES}
    if args.table and args.table not in table_names:
        raise SystemExit(
            f"Unknown --table '{args.table}'. Choose from: {', '.join(table_names)}"
        )
    static_base = (args.static_base_url or DEFAULT_STATIC_BASE_URL).rstrip("/")

    if args.execute and args.dry_run:
        raise SystemExit("Use EITHER --dry-run (default) OR --execute, not both.")

    # --- Logging ----------------------------------------------------------
    log_file = os.path.join(args.out_dir, f"migrate_images_{mode}_{args.stamp}.log")
    handlers = [logging.StreamHandler(sys.stdout)]
    handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        handlers=handlers,
    )
    LOG.info("mode=%s | tables=%s | out_dir=%s",
             mode, args.table or "ALL", os.path.abspath(args.out_dir))

    # --- Credentials + clients -------------------------------------------
    load_env_file(MIGRATION_ENV_FILE)
    configure_cloudinary()
    conn = connect_mysql()

    manifest_path = os.path.join(
        args.out_dir, f"migrate_images_manifest_{mode}_{args.stamp}.csv")
    rollback_path = os.path.join(
        args.out_dir, f"migrate_images_rollback_{mode}_{args.stamp}.csv")
    mh, mw = open_csv(manifest_path, MANIFEST_FIELDS)
    rh, rw = open_csv(rollback_path, ROLLBACK_FIELDS)

    # in-run dedupe cache: (cloudinary_folder/public_id) -> (url, action)
    asset_cache = {}

    totals = {"scanned": 0, "already_absolute": 0, "blank": 0, "source_missing": 0,
              "upload_failed": 0, "verify_failed": 0, "updated": 0,
              "planned_update": 0, "reused": 0}

    processed = 0

    try:
        for cfg in TABLES:
            if args.table and cfg.table != args.table:
                continue
            LOG.info("== TABLE %s (folder %s) ==", cfg.table, cfg.cloudinary_folder)
            rows = fetch_image_rows(conn, cfg)
            LOG.info("   %d non-blank photo values", len(rows))
            for pk, old_value in rows:
                if args.limit and processed >= args.limit:
                    LOG.info("Reached --limit %d, stopping.", args.limit)
                    raise _StopProcessing()
                processed += 1
                totals["scanned"] += 1
                stamp = time.strftime("%Y-%m-%d %H:%M:%S")
                row = {
                    "migrated_at": stamp, "mode": mode, "table": cfg.table,
                    "id_column": cfg.id_col, "pk": pk,
                    "image_column": cfg.image_col, "old_value": old_value,
                }

                # 1) Blank -> preserve & skip (14 users have '' photos).
                if not old_value:
                    totals["blank"] += 1
                    row.update(status="skipped_blank",
                               detail="empty photo value, preserved")
                    mw.writerow(row)
                    continue

                # 2) Already absolute (http/https) -> NEVER touch.
                if ABSOLUTE_URL_RE.match(old_value):
                    totals["already_absolute"] += 1
                    row.update(status="skipped_absolute_url",
                               detail="value is already an absolute URL; not overwritten",
                               cloudinary_url=old_value)
                    mw.writerow(row)
                    continue

                # 3) Deterministic mapping for dedupe + idempotent re-runs.
                #    The FULL public_id includes the folder so Cloudinary
                #    lookups, verification and the final asset path are
                #    unambiguous (e.g. hotel_management/rooms/master5).
                bare_public_id = sanitize_public_id(old_value)
                public_id = f"{cfg.cloudinary_folder}/{bare_public_id}"
                cache_key = public_id

                # 4) Resolve/download the original bytes (retry-capable).
                source_kind = ""
                source_ref = ""
                try:
                    data, source_kind, source_ref = download_source(
                        cfg, old_value, static_base, args.source_dir, args.retries
                    )
                except Exception as exc:  # noqa: BLE001
                    totals["source_missing"] += 1
                    row.update(
                        status="skipped_source_missing",
                        detail=f"original not found: {exc}",
                        public_id=public_id,
                        source_url_or_path=(
                            source_ref
                            if source_ref
                            else source_url_for(cfg, old_value, static_base)
                        ),
                    )
                    mw.writerow(row)
                    LOG.warning("   pk=%s %s | source missing: %s", pk, old_value, exc)
                    continue

                row.update(public_id=public_id,
                           source_kind=source_kind,
                           source_url_or_path=source_ref,
                           source_size_bytes=len(data),
                           source_sha256=sha256_bytes(data),
                           retries=args.retries)


                # 5) Dedupe: same filename -> same public_id within this run.
                #    Cache entries are (url, action, verified) tuples so that a
                #    duplicate row (e.g. master5.jpg) still verifies the asset
                #    before its update instead of blindly trusting the cache.
                if cache_key in asset_cache:
                    cloudinary_url, action, verified = asset_cache[cache_key]
                elif args.dry_run:
                    # Read-only existence check only — no upload in dry-run.
                    already = _resource_exists(public_id)
                    cloudinary_url = (
                        get_cloudinary_url(public_id) if already else "")
                    action = ("would_reuse_existing_asset" if already
                              else "would_upload")
                    verified = False
                    asset_cache[cache_key] = (cloudinary_url, action, verified)
                else:
                    try:
                        cloudinary_url, action = upload_or_reuse(
                            data, public_id, args.retries)
                    except Exception as exc:  # noqa: BLE001
                        totals["upload_failed"] += 1
                        row.update(status="failed_upload", detail=f"{exc}")
                        mw.writerow(row)
                        LOG.error("   pk=%s %s | upload failed: %s", pk, old_value, exc)
                        continue
                    verified = False
                    asset_cache[cache_key] = (cloudinary_url, action, verified)

                # 6) Verify the EXACT asset before ANY database update. Runs for
                #    fresh uploads AND cache hits (duplicate filenames), so a
                #    row is never pointed at an asset we could not confirm.
                if (not args.dry_run) and (not args.no_verify) and not verified:
                    try:
                        verify_asset(public_id, cloudinary_url)
                    except Exception as exc:  # noqa: BLE001
                        totals["verify_failed"] += 1
                        row.update(status="failed_verification",
                                   cloudinary_url=cloudinary_url,
                                   detail=f"{exc}")
                        mw.writerow(row)
                        LOG.error("   pk=%s %s | verify failed: %s",
                                  pk, old_value, exc)
                        continue
                    verified = True
                    asset_cache[cache_key] = (cloudinary_url, action, verified)

                if action in ("reused_existing_asset", "would_reuse_existing_asset"):
                    totals["reused"] += 1

                # 7) DRY-RUN: stop here — never write to the DB.
                if args.dry_run:
                    totals["planned_update"] += 1
                    row.update(status="planned_update",
                               detail=f"{action} (dry-run only)",
                               cloudinary_url=cloudinary_url)
                    mw.writerow(row)
                    LOG.info("   [dry] pk=%s %s -> %s (%s)",
                             pk, old_value, cloudinary_url or "(upload)", action)
                    continue

                # 8) EXECUTE: defense-in-depth guards, then update, then commit.
                if not cloudinary_url or "res.cloudinary.com" not in cloudinary_url:
                    totals["upload_failed"] += 1
                    row.update(status="failed_invalid_url",
                               detail="refusing to write an invalid/non-Cloudinary URL",
                               cloudinary_url=cloudinary_url or "")
                    mw.writerow(row)
                    continue
                # Re-read the row right before writing (race-safety).
                current = dict(fetch_image_rows(conn, cfg)).get(pk, "")
                if ABSOLUTE_URL_RE.match(current):
                    totals["already_absolute"] += 1
                    row.update(status="skipped_absolute_url",
                               detail="row already updated by another process",
                               cloudinary_url=current)
                    mw.writerow(row)
                    continue
                try:
                    affected = update_image_url(conn, cfg, pk, cloudinary_url)
                    if affected != 1:
                        raise RuntimeError(
                            f"UPDATE affected {affected} rows, expected 1")
                    conn.commit()
                except Exception as exc:  # noqa: BLE001
                    conn.rollback()
                    totals["upload_failed"] += 1
                    row.update(status="failed_db_update",
                               detail=f"{exc}", cloudinary_url=cloudinary_url)
                    mw.writerow(row)
                    LOG.error("   pk=%s | DB update failed: %s", pk, exc)
                    continue

                totals["updated"] += 1
                row.update(status="updated", detail=action,
                           cloudinary_url=cloudinary_url)
                mw.writerow(row)
                # Rollback manifest: old value -> new value, for undo support.
                rw.writerow({"migrated_at": stamp, "mode": mode,
                             "table": cfg.table, "id_column": cfg.id_col,
                             "pk": pk, "image_column": cfg.image_col,
                             "old_value": old_value,
                             "new_value": cloudinary_url, "status": "committed"})
                rh.flush()
                mh.flush()
                LOG.info("   [exec] pk=%s %s -> %s (%s)",
                         pk, old_value, cloudinary_url, action)
    except _StopProcessing:
        pass
    finally:
        mh.close()
        rh.close()
        conn.close()

    LOG.info("SUMMARY %s: %s", mode, totals)
    LOG.info("manifest: %s", manifest_path)
    LOG.info("rollback: %s", rollback_path)
    LOG.info("log:      %s", log_file)
    return 0 if (totals["upload_failed"] == 0 and totals["verify_failed"] == 0) else 2


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true",
                      help="Audit/preview ONLY: reads the DB and remote sources, "
                           "uploads nothing, writes nothing. Default mode.")
    mode.add_argument("--execute", action="store_true",
                      help="Actually upload assets and update the photo column. "
                           "Run only after reviewing a dry run.")
    parser.add_argument("--table", choices=[cfg.table for cfg in TABLES],
                        help="Restrict processing to one table.")
    parser.add_argument("--limit", type=int, default=0, metavar="N",
                        help="Stop after N scanned rows (useful for testing).")
    parser.add_argument("--source-dir", default="", metavar="PATH",
                        help="Optional local folder mirroring the server static "
                             "dirs (e.g. the repo's 'static/'). Preferred source "
                             "over HTTP download.")
    parser.add_argument("--static-base-url", default=DEFAULT_STATIC_BASE_URL,
                        help="Base URL of the legacy static images. "
                             "Default: %(default)s")
    parser.add_argument("--retries", type=int, default=3,
                        help="Download/upload retries per asset (default: 3).")
    parser.add_argument("--no-verify", action="store_true",
                        help="Skip the post-upload verification HTTP call.")
    parser.add_argument("--out-dir", default=".",
                        help="Directory for CSV manifests and logs (must exist).")
    parser.add_argument("--verbose", action="store_true", help="Debug logging.")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    args.stamp = time.strftime("%Y%m%d_%H%M%S")
    if not os.path.isdir(args.out_dir):
        raise SystemExit(f"--out-dir does not exist: {args.out_dir}")
    if args.limit and args.limit < 1:
        raise SystemExit("--limit must be a positive integer.")
    return run_migration(args)


if __name__ == "__main__":
    raise SystemExit(main())