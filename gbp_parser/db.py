"""Postgres access: schema, places, photos."""
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from . import config


def connect():
    return psycopg.connect(**config.DB, autocommit=True, row_factory=dict_row)


def ensure_schema(conn):
    conn.execute(config.SCHEMA_FILE.read_text(encoding="utf-8"))


def upsert_place(conn, place):
    """Insert or update a place by its Google id; return (row id, folder).

    The folder is fixed when the place is first stored: its files are already there, so a later
    change of the name or address on Google must not move the place to another folder.
    """
    row = conn.execute(
        """
        INSERT INTO places (fid, mid, name, address, maps_url, folder)
        VALUES (%(fid)s, %(mid)s, %(name)s, %(address)s, %(maps_url)s, %(folder)s)
        ON CONFLICT (fid) DO UPDATE SET
            mid = EXCLUDED.mid, name = EXCLUDED.name, address = EXCLUDED.address,
            maps_url = EXCLUDED.maps_url
        RETURNING id, folder
        """,
        place,
    ).fetchone()
    return row["id"], row["folder"]


def upsert_photo(conn, place_id, item, position):
    """Insert a gallery item or refresh its metadata; the downloaded file columns are left alone."""
    conn.execute(
        """
        INSERT INTO photos (place_id, google_id, kind, contributor, upload_source, uploaded_at,
                            width, height, lat, lng, url, gallery_position, raw)
        VALUES (%(place_id)s, %(google_id)s, %(kind)s, %(contributor)s, %(upload_source)s, %(uploaded_at)s,
                %(width)s, %(height)s, %(lat)s, %(lng)s, %(url)s, %(position)s, %(raw)s)
        ON CONFLICT (place_id, google_id) DO UPDATE SET
            kind = EXCLUDED.kind, contributor = EXCLUDED.contributor, upload_source = EXCLUDED.upload_source,
            uploaded_at = EXCLUDED.uploaded_at, width = EXCLUDED.width, height = EXCLUDED.height,
            lat = EXCLUDED.lat, lng = EXCLUDED.lng, url = EXCLUDED.url,
            gallery_position = EXCLUDED.gallery_position, raw = EXCLUDED.raw, last_seen_at = now()
        """,
        {
            "place_id": place_id, "google_id": item.google_id, "kind": item.kind,
            "contributor": item.contributor, "upload_source": item.upload_source,
            "uploaded_at": item.uploaded_at, "width": item.width, "height": item.height,
            "lat": item.lat, "lng": item.lng, "url": item.url, "position": position,
            "raw": Jsonb(item.raw),
        },
    )


def delete_photos_not_listed(conn, place_id, listed_google_ids):
    """Delete the place's rows whose item Google no longer lists; return the deleted rows."""
    return conn.execute(
        """
        DELETE FROM photos WHERE place_id = %s AND NOT (google_id = ANY(%s))
        RETURNING google_id, kind, contributor, file_path
        """,
        (place_id, list(listed_google_ids)),
    ).fetchall()


def finish_place_sync(conn, place_id, google_claims, google_listed):
    conn.execute(
        "UPDATE places SET google_claims = %s, google_listed = %s, last_synced_at = now() WHERE id = %s",
        (google_claims, google_listed, place_id),
    )


def owner_photos_without_file(conn, place_id):
    return conn.execute(
        """
        SELECT id, google_id, url, uploaded_at FROM photos
        WHERE place_id = %s AND kind = 'photo' AND contributor = 'owner' AND file_path IS NULL
        ORDER BY gallery_position
        """,
        (place_id,),
    ).fetchall()


def mark_downloaded(conn, photo_id, file_path, file_bytes, file_sha256):
    conn.execute(
        """
        UPDATE photos SET file_path = %s, file_bytes = %s, file_sha256 = %s, downloaded_at = now()
        WHERE id = %s
        """,
        (file_path, file_bytes, file_sha256, photo_id),
    )


def upsert_post(conn, place_id, post, position):
    """Insert a post or refresh its data; the downloaded file columns are left alone."""
    conn.execute(
        """
        INSERT INTO posts (place_id, google_id, posted_at, text, link, image_count, image_url, list_position, raw)
        VALUES (%(place_id)s, %(google_id)s, %(posted_at)s, %(text)s, %(link)s, %(image_count)s,
                %(image_url)s, %(position)s, %(raw)s)
        ON CONFLICT (place_id, google_id) DO UPDATE SET
            posted_at = EXCLUDED.posted_at, text = EXCLUDED.text, link = EXCLUDED.link,
            image_count = EXCLUDED.image_count, image_url = EXCLUDED.image_url,
            list_position = EXCLUDED.list_position, raw = EXCLUDED.raw, last_seen_at = now()
        """,
        {
            "place_id": place_id, "google_id": post.google_id, "posted_at": post.posted_at,
            "text": post.text, "link": post.link, "image_count": post.image_count,
            "image_url": post.image_url, "position": position, "raw": Jsonb(post.raw),
        },
    )


def posts_without_file(conn, place_id):
    return conn.execute(
        """
        SELECT id, google_id, image_url, posted_at FROM posts
        WHERE place_id = %s AND image_url IS NOT NULL AND file_path IS NULL
        ORDER BY posted_at DESC
        """,
        (place_id,),
    ).fetchall()


def mark_post_downloaded(conn, post_id, file_path, file_bytes, file_sha256):
    conn.execute(
        """
        UPDATE posts SET file_path = %s, file_bytes = %s, file_sha256 = %s, downloaded_at = now()
        WHERE id = %s
        """,
        (file_path, file_bytes, file_sha256, post_id),
    )


def post_counts(conn):
    """Per place id: how many posts are stored, how many have a picture file, when posts were last synced."""
    rows = conn.execute(
        """
        SELECT place_id, count(*) AS posts, count(file_path) AS files, max(last_seen_at) AS synced
        FROM posts GROUP BY place_id
        """
    ).fetchall()
    return {row["place_id"]: row for row in rows}


def status(conn):
    return conn.execute(
        """
        SELECT p.id, p.folder, p.google_claims, p.google_listed, p.last_synced_at,
               count(ph.id)                                                              AS rows,
               count(*) FILTER (WHERE ph.kind = 'street_view')                           AS panoramas,
               count(*) FILTER (WHERE ph.kind = 'photo' AND ph.contributor = 'owner')    AS owner_photos,
               count(*) FILTER (WHERE ph.kind = 'photo' AND ph.contributor = 'owner'
                                AND ph.file_path IS NOT NULL)                            AS downloaded,
               count(*) FILTER (WHERE ph.kind = 'photo' AND ph.contributor = 'customer') AS customer_photos,
               count(*) FILTER (WHERE ph.kind = 'video')                                 AS videos,
               coalesce(sum(ph.file_bytes), 0)::bigint                                   AS bytes
        FROM places p LEFT JOIN photos ph ON ph.place_id = p.id
        GROUP BY p.id ORDER BY p.id
        """
    ).fetchall()
