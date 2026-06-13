-- DA10 — PostgreSQL schema (Phase 1). Contract §3.1 build plan.
-- Áp: psql -h localhost -U da10 -d da10 -f db/schema.sql  (hoặc tự động trong pipeline/ingest_db.py)
-- hotel_id = int Agoda (R2). amenities = UNION mọi field amenity (R17).

CREATE TABLE IF NOT EXISTS hotels (
  id                 BIGINT PRIMARY KEY,            -- Agoda hotel_id
  name               TEXT,
  accommodation_type VARCHAR(100),
  star_rating        NUMERIC(3,1),
  is_luxury          BOOLEAN,
  address            TEXT,
  city               TEXT,
  area               TEXT,
  country            TEXT,
  latitude           DOUBLE PRECISION,
  longitude          DOUBLE PRECISION,
  review_score       NUMERIC(3,1),
  review_count       INTEGER,
  description        TEXT,
  amenities          TEXT[],                        -- R17: union amenities + _general/_leisure/_dining + amenity_groups
  suitable_for       TEXT[],
  useful_info        JSONB,
  reviews_detail     JSONB,
  policy_notes       TEXT[],                        -- R14: secondary.hotel_policy.policyNotes
  faq                JSONB,                         -- list {question, answer, category}
  images             TEXT[],
  source_url         TEXT
);

CREATE TABLE IF NOT EXISTS rooms (
  id            BIGSERIAL PRIMARY KEY,
  hotel_id      BIGINT REFERENCES hotels(id) ON DELETE CASCADE,
  room_type_id  BIGINT,
  name          TEXT,
  price         NUMERIC(15,2),                      -- R14: = price_per_night
  room_size     TEXT,
  max_occupancy INTEGER,
  bed_type      TEXT,
  room_view     TEXT,
  room_amenities TEXT[],
  images        TEXT[],
  review_score  NUMERIC(3,1)
);

CREATE TABLE IF NOT EXISTS nearby_places (
  id          BIGSERIAL PRIMARY KEY,
  hotel_id    BIGINT REFERENCES hotels(id) ON DELETE CASCADE,
  seq         INTEGER,                              -- R3: index (nguồn không có id)
  name        TEXT,
  type        TEXT,
  distance_km NUMERIC(6,2)
);

CREATE TABLE IF NOT EXISTS activities (
  id           BIGSERIAL PRIMARY KEY,
  hotel_id     BIGINT REFERENCES hotels(id) ON DELETE CASCADE,
  activity_id  BIGINT,
  title        TEXT,
  description  TEXT,
  price_amount NUMERIC(15,2),
  review_score NUMERIC(3,1)
);

-- Indexes phục vụ SQL pre-filter (Phase 4)
CREATE INDEX IF NOT EXISTS idx_hotels_city        ON hotels(city);
CREATE INDEX IF NOT EXISTS idx_hotels_acc          ON hotels(accommodation_type);
CREATE INDEX IF NOT EXISTS idx_hotels_amenities    ON hotels USING GIN(amenities);
CREATE INDEX IF NOT EXISTS idx_hotels_suitable_for ON hotels USING GIN(suitable_for);
CREATE INDEX IF NOT EXISTS idx_rooms_hotel_id      ON rooms(hotel_id);
CREATE INDEX IF NOT EXISTS idx_nearby_hotel_id     ON nearby_places(hotel_id);
CREATE INDEX IF NOT EXISTS idx_activities_hotel_id ON activities(hotel_id);
