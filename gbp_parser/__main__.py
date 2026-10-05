"""Usage:  python main.py sync     pull galleries of all places from places.json, download owner photos
        python main.py status   what is in the database

`python -m gbp_parser sync` does the same.
"""
import json
import re
import sys
import urllib.parse
from collections import Counter

from . import config, db
from .download import download_original
from .maps_client import MapsSession
from .parse import parse_item

FORBIDDEN_IN_FOLDER = '<>:"/\\|?*'


def load_places():
    """Read places.json and derive the Google ids and the data folder from each entry."""
    places = json.loads(config.PLACES_FILE.read_text(encoding="utf-8"))
    for place in places:
        url = urllib.parse.unquote(place["maps_url"])
        place["fid"] = re.search(r"!1s(0x[0-9a-f]+:0x[0-9a-f]+)", url).group(1)
        mid = re.search(r"!16s(/g/[^!?]+)", url)
        place["mid"] = mid.group(1) if mid else None
        folder = f"{place['name']} - {place['address']}"
        place["folder"] = "".join(c for c in folder if c not in FORBIDDEN_IN_FOLDER)
    return places


def sync():
    places = load_places()
    with db.connect() as conn, MapsSession() as maps:
        db.ensure_schema(conn)
        for place in places:
            print(f"\n{place['folder']}")
            shown_name, shown_address = maps.open_place(place["maps_url"])
            # Several places share a name, so both must match exactly what places.json says.
            if shown_name != place["name"] or not shown_address.startswith(place["address"] + ","):
                print(f"  SKIPPED: Google shows {shown_name!r} at {shown_address!r}")
                continue
            place_id = db.upsert_place(conn, place)

            raw_items, google_total = maps.list_gallery(place["fid"], place["mid"])
            items = [item for item in map(parse_item, raw_items) if item.kind != "street_view"]
            for position, item in enumerate(items):
                db.upsert_photo(conn, place_id, item, position)
            db.finish_place_sync(conn, place_id, google_total)
            counts = Counter((item.kind, item.contributor) for item in items)
            print(f"  Google reports {google_total} gallery items, listed {len(raw_items)}: "
                  + ", ".join(f"{n} {contributor} {kind}" for (kind, contributor), n in sorted(counts.items())))

            pending = db.owner_photos_without_file(conn, place_id)
            for number, photo in enumerate(pending, 1):
                path, size, sha256 = download_original(photo["url"], place["folder"],
                                                       photo["uploaded_at"], photo["google_id"])
                db.mark_downloaded(conn, photo["id"], path, size, sha256)
                print(f"  downloaded {number}/{len(pending)}  {path}", flush=True)
            if not pending:
                print("  no new owner photos to download")


def status():
    with db.connect() as conn:
        db.ensure_schema(conn)
        for row in db.status(conn):
            synced = row["last_synced_at"].strftime("%Y-%m-%d %H:%M") if row["last_synced_at"] else "never"
            print(f"{row['folder']}\n"
                  f"  owner photos {row['owner_photos']} (files on disk {row['downloaded']}, "
                  f"{row['bytes'] / 1e6:.0f} MB), customer photos {row['customer_photos']}, "
                  f"videos {row['videos']}; Google reports {row['google_total']}; synced {synced}")


COMMANDS = {"sync": sync, "status": status}


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        sys.exit(__doc__)
    COMMANDS[sys.argv[1]]()


if __name__ == "__main__":
    main()
