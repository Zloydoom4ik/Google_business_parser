"""Does the list the Maps page itself loads (pages of 20) leave out the duplicate copies?

    python checks/dup_vs_paging.py

For the first place in places.json, compares the photo ids Google returns with page size 20 (what the
Maps page uses) and 100 (what the parser uses) against the byte-identical files already in the database.
Run `python main.py sync` first.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gbp_parser import db, maps_client  # noqa: E402
from gbp_parser.__main__ import load_places  # noqa: E402

place = load_places()[0]


def listing(session, size):
    maps_client.PAGE_SIZE = size
    items, _ = session.list_gallery(place["fid"], place["mid"])
    return [item[0] for item in items if item[1] != 0]      # item[1] == 0 is Street View


with maps_client.MapsSession() as session:
    session.open_place(place["maps_url"])
    small = listing(session, 20)
    time.sleep(1)
    big = listing(session, 100)

with db.connect() as conn:
    rows = conn.execute(
        """SELECT google_id, contributor, file_sha256,
                  count(*) OVER (PARTITION BY file_sha256) AS copies
           FROM photos WHERE place_id = (SELECT id FROM places WHERE fid = %s)""", (place["fid"],)).fetchall()
info = {r["google_id"]: r for r in rows}

missing = [i for i in big if i not in set(small)]
print(place["folder"])
print(f"photos with pages of 100: {len(big)}; with pages of 20: {len(small)}; left out by pages of 20: {len(missing)}")
for kind in ("owner", "customer"):
    ids = [i for i in missing if info[i]["contributor"] == kind]
    copies = [i for i in ids if info[i]["file_sha256"] and info[i]["copies"] > 1]
    print(f"  left out, {kind}: {len(ids)}; of them a copy of another photo: {len(copies)}")

small_owner = [info[i]["file_sha256"] for i in small if info[i]["contributor"] == "owner"]
print(f"owner photos in the pages-of-20 list: {len(small_owner)}, distinct files among them: {len(set(small_owner))}")
