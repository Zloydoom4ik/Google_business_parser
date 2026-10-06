"""The places to work on: places.json, plus what Google itself says about each of them."""
import json
import re
import urllib.parse

from . import config, db

FORBIDDEN_IN_FOLDER = '<>:"/\\|?*'
NO_NAME = "no_name"
NO_ADDRESS = "no_address"       # service-area businesses show no street address on Google


def load_places():
    """Read places.json and derive the Google ids from each link.

    An entry needs only "maps_url". "name" and "address" are optional: when given, they must match Google.
    """
    places = json.loads(config.PLACES_FILE.read_text(encoding="utf-8"))
    for place in places:
        url = urllib.parse.unquote(place["maps_url"])
        place["fid"] = re.search(r"!1s(0x[0-9a-f]+:0x[0-9a-f]+)", url).group(1)
        mid = re.search(r"!16s(/g/[^!?]+)", url)
        place["mid"] = mid.group(1) if mid else None
    return places


def fill_from_google(place, shown_name, shown_address):
    """Set the place's name, address and folder from places.json and from what Google shows.

    Returns None, or the reason to skip the place: places.json gives a name or an address
    and Google shows a different one.
    """
    # Several places share a name, so whatever places.json gives must match Google exactly.
    if "name" in place and place["name"] != shown_name:
        return f"Google shows the name {shown_name!r}"
    if "address" in place and not (shown_address or "").startswith(place["address"] + ","):
        return f"Google shows the address {shown_address!r}"
    place["name"] = shown_name or NO_NAME
    place.setdefault("address", shown_address.split(",")[0] if shown_address else NO_ADDRESS)
    folder = f"{place['name']} - {place['address']}"
    place["folder"] = "".join(c for c in folder if c not in FORBIDDEN_IN_FOLDER).rstrip(" .")
    return None


def verified_places(conn, maps):
    """Yield (place, its row id) for every place in places.json, skipping those that fail the check."""
    for place in load_places():
        problem = fill_from_google(place, *maps.open_place(place["maps_url"]))
        if problem:
            print(f"\n{place['maps_url']}\n  SKIPPED: {problem}")
            continue
        place_id, place["folder"] = db.upsert_place(conn, place)
        print(f"\n{place['folder']}")
        yield place, place_id
