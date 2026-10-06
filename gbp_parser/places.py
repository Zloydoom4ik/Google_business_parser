"""The places to work on: places.json, plus the check that every link leads to the place it claims."""
import json
import re
import urllib.parse

from . import config, db

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


def verified_places(conn, maps):
    """Yield (place, its row id) for every place whose name and address on Google match places.json."""
    for place in load_places():
        print(f"\n{place['folder']}")
        shown_name, shown_address = maps.open_place(place["maps_url"])
        # Several places share a name, so both must match exactly what places.json says.
        if shown_name != place["name"] or not shown_address.startswith(place["address"] + ","):
            print(f"  SKIPPED: Google shows {shown_name!r} at {shown_address!r}")
            continue
        yield place, db.upsert_place(conn, place)
