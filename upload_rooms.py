"""Bulk-upload local room images to Cloudinary and update the rooms table.

Required environment variables:
    CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET
    MYSQL_PASSWORD

Optional MySQL variables: MYSQL_HOST, MYSQL_USER, MYSQL_DATABASE
"""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

import cloudinary
import cloudinary.uploader
import pymysql
import pymysql.cursors


ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
CLOUDINARY_FOLDER = "hotel rooms"


def configure_cloudinary() -> None:
    cloudinary.config(
        cloud_name=os.environ["CLOUDINARY_CLOUD_NAME"],
        api_key=os.environ["CLOUDINARY_API_KEY"],
        api_secret=os.environ["CLOUDINARY_API_SECRET"],
        secure=True,
    )


def connect_to_mysql():
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "mysql-victordesigner.alwaysdata.net"),
        user=os.getenv("MYSQL_USER", "victordesigner"),
        password=os.environ["MYSQL_PASSWORD"],
        database=os.getenv("MYSQL_DATABASE", "victordesigner_fullstack"),
        cursorclass=pymysql.cursors.DictCursor,
    )


def find_room_id(cursor, image_path: Path) -> int | None:
    """Match by existing photo filename, or by a numeric roomN filename."""
    filename = image_path.name.lower()
    cursor.execute("SELECT room_id, photo FROM rooms")
    rooms = cursor.fetchall()

    for room in rooms:
        stored_photo = (room["photo"] or "").split("/")[-1].lower()
        if stored_photo == filename or Path(stored_photo).stem == image_path.stem.lower():
            return room["room_id"]

    numeric_match = re.fullmatch(r"room[-_ ]?(\d+)", image_path.stem, re.IGNORECASE)
    if numeric_match:
        room_id = int(numeric_match.group(1))
        cursor.execute("SELECT room_id FROM rooms WHERE room_id = %s", (room_id,))
        if cursor.fetchone():
            return room_id

    return None


def upload_rooms(image_folder: Path) -> None:
    configure_cloudinary()
    image_paths = sorted(
        path for path in image_folder.iterdir()
        if path.is_file() and path.suffix.lower() in ALLOWED_EXTENSIONS
    )

    if not image_paths:
        print(f"No room images found in {image_folder}")
        return

    connection = connect_to_mysql()
    try:
        with connection.cursor() as cursor:
            for image_path in image_paths:
                room_id = find_room_id(cursor, image_path)
                if room_id is None:
                    print(f"SKIPPED {image_path.name}: no matching room record")
                    continue

                try:
                    result = cloudinary.uploader.upload(
                        str(image_path),
                        folder=CLOUDINARY_FOLDER,
                        resource_type="image",
                        use_filename=True,
                        unique_filename=True,
                    )
                    secure_url = result["secure_url"]
                    cursor.execute(
                        "UPDATE rooms SET photo = %s WHERE room_id = %s",
                        (secure_url, room_id),
                    )
                    connection.commit()
                    print(f"SUCCESS {image_path.name} -> room {room_id}: {secure_url}")
                except Exception as error:
                    connection.rollback()
                    print(f"FAILED {image_path.name}: {error}")
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--folder",
        type=Path,
        default=Path(__file__).resolve().parent / "static" / "rooms",
        help="Local folder containing room images",
    )
    args = parser.parse_args()

    if not args.folder.is_dir():
        raise SystemExit(f"Room image folder does not exist: {args.folder}")

    upload_rooms(args.folder)


if __name__ == "__main__":
    main()
