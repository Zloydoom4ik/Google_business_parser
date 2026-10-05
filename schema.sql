-- Applied on every run; every statement must be safe to repeat.

CREATE TABLE IF NOT EXISTS places (
    id             serial PRIMARY KEY,
    fid            text NOT NULL UNIQUE,       -- Google Maps place id, "0x...:0x..."
    mid            text,                       -- "/g/..." id from the same Maps URL
    name           text NOT NULL,
    address        text NOT NULL,
    maps_url       text NOT NULL,
    folder         text NOT NULL UNIQUE,       -- directory under data/
    google_total   integer,                    -- gallery size Google reports (includes Street View)
    last_synced_at timestamptz
);

-- One row per gallery item of a place (photos and videos; Street View is not stored).
CREATE TABLE IF NOT EXISTS photos (
    id               bigserial PRIMARY KEY,
    place_id         integer NOT NULL REFERENCES places (id),
    google_id        text NOT NULL,
    kind             text NOT NULL,            -- photo | video
    contributor      text NOT NULL,            -- owner | customer | unknown
    upload_source    text,                     -- Google's upload channel, e.g. bizbuilder:gmb_on_local_universal_desktop
    uploaded_at      timestamp,                -- hour precision, time zone not stated by Google
    width            integer,
    height           integer,
    lat              double precision,
    lng              double precision,
    url              text NOT NULL,            -- without a size suffix; "=s0" appended gives the original
    gallery_position integer,                  -- order in the public gallery at the last sync
    file_path        text,                     -- relative to data/, NULL until downloaded
    file_bytes       bigint,
    file_sha256      text,
    downloaded_at    timestamptz,
    raw              jsonb NOT NULL,           -- the item exactly as Google returned it
    first_seen_at    timestamptz NOT NULL DEFAULT now(),
    last_seen_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (place_id, google_id)
);

CREATE INDEX IF NOT EXISTS photos_place_contributor_idx ON photos (place_id, contributor);
