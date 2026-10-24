# IMAGE_ASSET_INVENTORY — Tasks C (homepage & static assets)

Status: **INVENTORY ONLY — nothing below has been changed.** Decisions on the
"Needs confirmation" sections are left open until you confirm the intended
source/usage of each asset group.

Legend for the **Migrate?** column:
- **YES (DB)** — asset is referenced by a database row; the row's `photo`
  value is migrated by `migrate_images.py`.
- **YES (code)** — hard-coded in frontend code and identical to a DB-referenced
  asset; after DB migration it should point at the new Cloudinary URL.
- **LOCAL OK** — branding/PWA/CSS; can stay as a bundled/static asset.
- **CONFIRM** — unused or ambiguous; keep as-is until confirmed.

## 1. Database-backed images (81 unique files) — migrate via `migrate_images.py`

| Table | Column | Folder on server | Cloudinary folder | Count |
|---|---|---|---|---|
| `dining` | `dining.photo` | `static/images/` | `hotel_management/dining` | 36 |
| `gallery` | `gallery.photo` | `static/gallery/` | `hotel_management/gallery` | 16 |
| `rooms` | `rooms.photo` | `static/rooms/` | `hotel_management/rooms` | 28 (27 unique; `master5.jpg` twice) |
| `users` | `users.photo` | `static/profiles/` | `hotel_management/profiles` | 2 (14 users have `''`, preserved) |

Full id→filename lists and the 81/81 reachability proof live in the Phase 1
audit. **Migrate?** YES (DB). No `static/` file is deleted after migration.

## 2. Home.jsx carousels — hard-coded static URLs

All refer to
`https://victordesigner.alwaysdata.net/static/...` in `src/components/Home.jsx`:

| Line | Asset | Also a DB row? | Migrate? |
|---|---|---|---|
| 107 | `gallery/overview.jpg` | yes — gallery id 16 | YES (code) |
| 110 | `gallery/fountain.jpg` | yes — gallery id 18 | YES (code) |
| 113 | `gallery/path.jpg` | yes — gallery id 17 | YES (code) |
| 116 | `gallery/pool.jpg` | yes — gallery id 1 | YES (code) |
| 129 | `rooms/master1.jpg` | **no** — no rooms row uses it | CONFIRM (upload once or keep local) |
| 132 | `rooms/master2.jpg` | yes — room id 2 | YES (code) |
| 149 | `images/dinner2.avif` | yes — dining id 23 | YES (code) |
| 152 | `images/break1.jpg` | yes — dining id 4 | YES (code) |
| 169 | `gallery/pool.jpg` | yes — gallery id 1 | YES (code) |
| 172 | `gallery/parking.jpg` | yes — gallery id 4 | YES (code) |
| 175 | `gallery/playground.jpg` | yes — gallery id 5 | YES (code) |
| 192 | `gallery/control room.jpg` | yes — gallery id 2 | YES (code) |
| 195 | `gallery/surgent.jpg` | yes — gallery id 3 | YES (code) |
| 198 | `gallery/dog.jpg` | yes — gallery id 19 | YES (code) |

Recommendation: after the DB migration, replace these with the same Cloudinary
secure URLs (12 of 13 already exist in the DB; only `rooms/master1.jpg` needs a
one-off upload). **Not changed yet — needs your OK.**

## 3. `public/images/` — CRA bundled static assets

| File | Referenced anywhere in `src/`? | Migrate? |
|---|---|---|
| `pool.jpg` | No direct reference (same bytes as `static/gallery/pool.jpg`) | CONFIRM |
| `parking.jpg` | No direct reference | CONFIRM |
| `playground.jpg` | No direct reference | CONFIRM |
| `milkway.jpg` | No direct reference — appears unused | CONFIRM |

These are build-time bundled assets (`%PUBLIC_URL%/...`). The UI renders the
server `static/` URLs instead, so they can stay local (unused) or be dropped
later once the server paths are retired — **no Cloudinary needed**.

## 4. Branding / PWA / app shell — LOCAL OK (no migration)

| Asset | Used by |
|---|---|
| `public/favicon.ico` | `index.html` line 5 |
| `public/logo192.png`, `public/logo512.png` | `index.html` line 12, `manifest.json` icons, PWA install |
| `public/manifest.json`, `public/robots.txt` | PWA metadata |
| `src/logo.svg` | default CRA logo (unused in a route) |
| `public/index.html` metadata / theme-color | static |

These are branding, not content photos. **LOCAL OK.**

## 5. CSS backgrounds — nothing to migrate

`src/App.css` uses only color values (`background-color`, `background: #111`)
and has **no `url(...)` image references**. Other CSS is Bootstrap/React
dependencies. **LOCAL OK — nothing to do.**

## 6. Backend `static/` directories (repo + server)

Files present in this repo's `static/` tree (valid JPEGs; subset also on server):

| File | DB-referenced today? | Migrate? |
|---|---|---|
| `static/gallery/pool.jpg` | yes — gallery id 1 | YES (DB) |
| `static/rooms/master2.jpg`, `master5.jpg` | yes — rooms 2 / 5 & 21 | YES (DB) |
| `static/images/break4.jpg` | yes — dining id 1 | YES (DB) |
| `static/gallery/fish.jpg`, `master3.jpg` | no | CONFIRM (leftover from old dump) |
| `static/images/fish.jpg`, `chipsburger.jpg`, `beverage.jpg`, `cocktail.jpg`, `dining_1_beverage.jpg`, `juices.jpg`, `master1.jpg` | no | CONFIRM (leftovers / duplicates) |
| `static/rooms/board3.jpg`, `chicken.jpg`, `master1.jpg` | no | CONFIRM (leftovers) |
| `static/profiles/IMG-20260107-WA0000.jpg`, `IMG_20250403_181657.jpg` | no (DB uses newer `IMG-2026*` files) | CONFIRM (leftovers) |

`static/rooms/master1.jpg` == `static/images/master1.jpg` (same photo, two
places); the Home carousel references the `static/rooms/` copy.

**Server-side note:** the 77 originals that exist only on AlwaysData are served
by URLs verified 81/81 (HTTP 200, correct `image/*` type), so the migration
script can pull them directly. After cutover the server `static/*` folders may
be retired or kept as backup — your call.

## 7. Open decisions (for your confirmation)

1. Fold the `Home.jsx` hard-coded carousels over to Cloudinary (12 DB + 1 extra
   `master1.jpg`) — include in the Task B patch or as a separate edit?
2. Delete/keep the unused `public/images/*` and leftover `static/*` files —
   currently everything is kept.
3. Retire the AlwaysData `static/` folders after cutover, or keep as offline
   backup? Currently kept.
