-- Applied on every run; every statement must be safe to repeat.

CREATE TABLE IF NOT EXISTS places (
    id             serial PRIMARY KEY,
    fid            text NOT NULL UNIQUE,       -- Google Maps place id, "0x...:0x..."
    mid            text,                       -- "/g/..." id from the same Maps URL
    name           text NOT NULL,
    address        text NOT NULL,
    maps_url       text NOT NULL,
    folder         text NOT NULL UNIQUE,       -- directory under data/
    google_claims  integer,                    -- gallery size Google states in its answer
    google_listed  integer,                    -- items Google actually returned at the last sync;
                                               -- equals the place's row count in photos
    last_synced_at timestamptz
);

-- One row per gallery item of a place: everything Google listed, Street View panoramas included.
CREATE TABLE IF NOT EXISTS photos (
    id               bigserial PRIMARY KEY,
    place_id         integer NOT NULL REFERENCES places (id),
    google_id        text NOT NULL,
    kind             text NOT NULL,            -- photo | video | street_view
    contributor      text NOT NULL,            -- owner | customer | google | unknown
    upload_source    text,                     -- Google's upload channel, e.g. bizbuilder:gmb_on_local_universal_desktop
    uploaded_at      timestamp,                -- hour precision, time zone not stated by Google
    width            integer,
    height           integer,
    lat              double precision,
    lng              double precision,
    url              text NOT NULL,            -- photo/video: no size suffix, "=s0" appended gives the original;
                                               -- street_view: link to the panorama's preview picture
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

-- One row per post ("update") of a place. Google Maps lists only the 10 latest posts of a place;
-- a post that drops out of that list keeps its row.
CREATE TABLE IF NOT EXISTS posts (
    id            bigserial PRIMARY KEY,
    place_id      integer NOT NULL REFERENCES places (id),
    google_id     text NOT NULL,
    posted_at     timestamptz,                 -- exact to the second
    text          text,
    link          text,                        -- public page of the post
    image_count   integer NOT NULL,            -- pictures attached to the post
    image_url     text,                        -- first picture, no size suffix; "=s0" appended gives the original
    list_position integer,                     -- order in Google's list at the last sync, 0 = newest
    file_path     text,                        -- first picture, relative to data/, NULL until downloaded
    file_bytes    bigint,
    file_sha256   text,
    downloaded_at timestamptz,
    raw           jsonb NOT NULL,              -- the post exactly as Google returned it
    first_seen_at timestamptz NOT NULL DEFAULT now(),
    last_seen_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (place_id, google_id)
);
