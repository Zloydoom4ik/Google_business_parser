"""Posts ("updates") of a place: the ones Google Maps lists, with their pictures.

Google Maps lists only the 10 most recent posts of a place; older ones cannot be reached this way.
A post that drops out of that list stays in the database: leaving the list does not mean it was deleted.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

from . import db
from .download import download_original
from .maps_client import MapsSession
from .parse import dig
from .places import verified_places


@dataclass
class Post:
    google_id: str
    posted_at: datetime | None      # exact to the second
    text: str | None
    link: str | None                # public page of the post
    image_count: int
    image_url: str | None           # first picture, without the size suffix; "=s0" gives the original
    raw: list


def parse_post(raw):
    """Turn one raw post (a nested list, as Google sends it) into named fields."""
    posted = dig(raw, 2, 0)
    images = dig(raw, 5) or []
    first_image = dig(images, 0, 0)
    return Post(
        google_id=raw[6],
        posted_at=datetime.fromtimestamp(posted, timezone.utc) if posted else None,
        text=dig(raw, 1, 0, 0, 0),
        link=dig(raw, 9),
        image_count=len(images),
        image_url=first_image.rsplit("=", 1)[0] if first_image else None,
        raw=raw,
    )


def sync_posts():
    with db.connect() as conn, MapsSession() as maps:
        db.ensure_schema(conn)
        for place, place_id in verified_places(conn, maps):
            posts = [parse_post(raw) for raw in maps.list_posts(place["fid"])]
            for position, post in enumerate(posts):
                db.upsert_post(conn, place_id, post, position)
            print(f"  Google lists {len(posts)} posts")
            for post in posts:
                if post.image_count > 1:
                    print(f"  post {post.google_id} has {post.image_count} pictures, only the first is downloaded")

            pending = db.posts_without_file(conn, place_id)
            for number, row in enumerate(pending, 1):
                path, size, sha256 = download_original(row["image_url"], place["folder"], row["posted_at"],
                                                       row["google_id"], subfolder="posts")
                db.mark_post_downloaded(conn, row["id"], path, size, sha256)
                print(f"  downloaded {number}/{len(pending)}  {path}", flush=True)
            if not pending:
                print("  no new post pictures to download")
