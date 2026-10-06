"""Usage:  python main.py sync         pull photo galleries of all places from places.json, download owner photos
        python main.py sync_posts   pull the latest posts of the same places, download their pictures
        python main.py status       what is in the database

`python -m gbp_parser <command>` does the same.
"""
import sys
from collections import Counter

from . import config, db
from .download import download_original
from .maps_client import MapsSession
from .parse import parse_item
from .places import verified_places
from .posts import sync_posts


def sync():
    with db.connect() as conn, MapsSession() as maps:
        db.ensure_schema(conn)
        for place, place_id in verified_places(conn, maps):
            raw_items, google_claims = maps.list_gallery(place["fid"], place["mid"])
            items = [parse_item(raw) for raw in raw_items]
            for position, item in enumerate(items):
                db.upsert_photo(conn, place_id, item, position)
            # Whatever Google no longer lists was removed from the profile: drop its row and its file.
            # An empty listing is treated as a failed answer, not as "everything was removed".
            if items:
                for gone in db.delete_photos_not_listed(conn, place_id, [item.google_id for item in items]):
                    if gone["file_path"]:
                        (config.DATA_DIR / gone["file_path"]).unlink(missing_ok=True)
                    print(f"  removed, no longer on Google: {gone['contributor']} {gone['kind']} "
                          f"{gone['google_id']}")
            db.finish_place_sync(conn, place_id, google_claims, len(items))
            counts = Counter((item.kind, item.contributor) for item in items)
            print(f"  Google claims {google_claims} gallery items, listed {len(items)}: "
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
        posts = db.post_counts(conn)
        for row in db.status(conn):
            synced = row["last_synced_at"].strftime("%Y-%m-%d %H:%M") if row["last_synced_at"] else "never"
            print(f"{row['folder']}\n"
                  f"  Google claims {row['google_claims']}, listed {row['google_listed']}; "
                  f"rows in the database {row['rows']}; synced {synced}\n"
                  f"  owner photos {row['owner_photos']} (files on disk {row['downloaded']}, "
                  f"{row['bytes'] / 1e6:.0f} MB), customer photos {row['customer_photos']}, "
                  f"videos {row['videos']}, panoramas {row['panoramas']}")
            if row["id"] in posts:
                p = posts[row["id"]]
                print(f"  posts {p['posts']} (picture files on disk {p['files']}); "
                      f"synced {p['synced'].strftime('%Y-%m-%d %H:%M')}")
            else:
                print("  posts: never synced")


COMMANDS = {"sync": sync, "sync_posts": sync_posts, "status": status}


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        sys.exit(__doc__)
    COMMANDS[sys.argv[1]]()


if __name__ == "__main__":
    main()
