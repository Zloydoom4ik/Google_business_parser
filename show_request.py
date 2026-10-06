"""Save one real exchange with Google Maps into request_example/ so it can be read by eye.

    python show_request.py

Takes the last place from places.json, sends the first gallery request and writes:
    1_request.json            what is sent
    2_response_raw.txt        what Google returns, untouched
    3_response_decoded.json   the same, unpacked into readable JSON
    4_one_photo.json          one photo: Google's raw record next to the fields the parser takes from it
"""
import dataclasses
import json
import urllib.parse

from gbp_parser import config
from gbp_parser.places import load_places
from gbp_parser.maps_client import RPC_URL, MapsSession, _payload
from gbp_parser.parse import parse_item

OUT = config.ROOT / "request_example"


def write(name, value):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2, default=str)
    (OUT / name).write_text(text, encoding="utf-8")


place = load_places()[-1]
with MapsSession() as maps:
    maps.open_place(place["maps_url"])
    body, response = maps.fetch_gallery_page(place["fid"], place["mid"])

OUT.mkdir(exist_ok=True)
envelope = json.loads(urllib.parse.parse_qs(body)["f.req"][0])
write("1_request.json", {
    "place": place["folder"],
    "method": "POST",
    "url": "https://www.google.com" + RPC_URL,
    "headers": {"content-type": "application/x-www-form-urlencoded;charset=UTF-8"},
    "body_as_sent": body,
    "body_decoded": {"rpc_name": envelope[0][0][0], "arguments": json.loads(envelope[0][0][1])},
})
write("2_response_raw.txt", response["text"])

data = _payload(response)
write("3_response_decoded.json", {
    "http_status": response["status"],
    "total_claimed_by_google": data[1],
    "next_page_token": data[5],
    "items_in_this_page": len(data[0] or []),
    "items": data[0],
})

raw = next(item for item in data[0] if item[1] != 0)
parsed = dataclasses.asdict(parse_item(raw))
del parsed["raw"]
write("4_one_photo.json", {"taken_by_parser": parsed, "raw_from_google": raw})
print(f"{place['folder']}: saved 4 files to {OUT}")
