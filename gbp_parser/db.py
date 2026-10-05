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
    """Insert or update a place by its Google id; return the row id."""
    row = conn.execute(
        """
        INSERT INTO places (fid, mid, name, address, maps_url, folder)
        VALUES (%(fid)s, %(mid)s, %(name)s, %(address)s, %(maps_url)s, %(folder)s)
        ON CONFLICT (fid) DO UPDATE SET
            mid = EXCLUDED.mid, name = EXCLUDED.name, address = EXCLUDED.address,
            maps_url = EXCLUDED.maps_url, folder = EXCLUDED.folder
        RETURNING id
        """,
        place,
    ).fetchone()
    return row["id"]


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


def finish_place_sync(conn, place_id, google_total):
    conn.execute(
        "UPDATE places SET google_total = %s, last_synced_at = now() WHERE id = %s",
        (google_total, place_id),
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


def status(conn):
    return conn.execute(
        """
        SELECT p.folder, p.google_total, p.last_synced_at,
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
