"""Turn one raw gallery item (a nested list, as Google sends it) into named fields."""
from dataclasses import dataclass
from datetime import datetime

# raw[21][6][0] says who added the item. Checked on 271 items of five places: 1 always comes with an
# upload source "bizbuilder:gmb_*" (the Business Profile dashboard), 2 with "photos:*" (a review or
# the Maps app), 3 with Street View.
CONTRIBUTORS = {1: "owner", 2: "customer", 3: "google"}


@dataclass
class GalleryItem:
    google_id: str
    kind: str                       # photo | video | street_view
    contributor: str                # owner | customer | google | unknown
    upload_source: str | None
    uploaded_at: datetime | None    # hour precision
    width: int | None
    height: int | None
    lat: float | None
    lng: float | None
    url: str                        # photo/video: without the size suffix, "=s0" gives the original
    raw: list


def _dig(value, *path):
    for index in path:
        if not isinstance(value, list) or index >= len(value) or value[index] is None:
            return None
        value = value[index]
    return value


def _uploaded_at(parts):
    if not parts:
        return None
    year, month, day, hour = (list(parts) + [None] * 4)[:4]
    return datetime(year, month or 1, day or 1, hour or 0)


def parse_item(raw):
    if raw[1] == 0:
        kind = "street_view"
    elif _dig(raw, 26):             # list of video encodings
        kind = "video"
    else:
        kind = "photo"
    url = _dig(raw, 6, 0) or ""
    width, height = _dig(raw, 6, 2) or (None, None)
    return GalleryItem(
        google_id=raw[0],
        kind=kind,
        contributor=CONTRIBUTORS.get(_dig(raw, 21, 6, 0), "unknown"),
        upload_source=_dig(raw, 21, 6, 5, 2),
        uploaded_at=_uploaded_at(_dig(raw, 21, 6, 8)),
        width=width,
        height=height,
        lat=_dig(raw, 8, 0, 2),
        lng=_dig(raw, 8, 0, 1),
        url=url if kind == "street_view" else url.rsplit("=", 1)[0],
        raw=raw,
    )
