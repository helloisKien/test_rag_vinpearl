"""DA10 — Phase 1: nạp data/hotel_*.json -> PostgreSQL (hotels, rooms, nearby_places, activities).

Chạy:
    docker compose up -d postgres
    python pipeline/ingest_db.py

Quyết định quan trọng (build plan):
  - hotel_id = int Agoda (R2).
  - hotels.amenities = UNION mọi field amenity (R17) — KHÔNG chỉ field `amenities` phẳng.
  - policy_notes = secondary.hotel_policy.policyNotes (R14).
  - rooms.price = price_per_night (R14); nearby_places.seq = index (R3).
Idempotent: tạo bảng nếu chưa có + TRUNCATE trước khi nạp lại.
"""
from __future__ import annotations
import glob
import json
import re
import sys
import os

import psycopg2
from psycopg2.extras import Json, execute_values

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import settings  # noqa: E402

AMENITY_FIELDS = ["amenities", "amenities_general", "amenities_leisure", "amenities_dining"]


# ----------------------------- helpers --------------------------------------
def to_float(v):
    try:
        if v is None or v == "":
            return None
        return float(str(v).replace(",", "."))
    except (ValueError, TypeError):
        return None


def to_int(v):
    f = to_float(v)
    return int(f) if f is not None else None


def str_list(v):
    """Ép về list[str] sạch (loại None/rỗng)."""
    if not v:
        return []
    if isinstance(v, str):
        v = [v]
    out = []
    for x in v:
        if x is None:
            continue
        s = str(x).strip()
        if s:
            out.append(s)
    return out


def parse_price(v):
    """activities.price có thể là số / chuỗi '500.000 VND' / dict -> NUMERIC hoặc None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict):
        for k in ("amount", "value", "price", "min"):
            if k in v:
                return parse_price(v[k])
        return None
    digits = re.sub(r"[^\d]", "", str(v))
    return float(digits) if digits else None


def amenities_union(d):
    """R17: hợp mọi nguồn amenity, dedupe, sort ổn định."""
    s = set()
    for f in AMENITY_FIELDS:
        s |= set(str_list(d.get(f)))
    ag = d.get("amenity_groups") or {}
    if isinstance(ag, dict):
        for v in ag.values():
            if isinstance(v, list):
                s |= set(str_list(v))
    return sorted(s)


def policy_notes(d):
    sec = d.get("secondary") or {}
    hp = sec.get("hotel_policy") or {}
    return str_list(hp.get("policyNotes"))


# ----------------------------- ingest ---------------------------------------
def run():
    files = sorted(glob.glob(os.path.join(settings.data_dir, "hotel_*.json")))
    if not files:
        sys.exit(f"Không thấy file nào ở {settings.data_dir}/hotel_*.json")

    conn = psycopg2.connect(settings.pg_dsn)
    conn.autocommit = False
    cur = conn.cursor()

    # 1. schema (idempotent) + truncate
    schema_path = os.path.join(os.path.dirname(__file__), "..", "db", "schema.sql")
    with open(schema_path, encoding="utf-8") as fh:
        cur.execute(fh.read())
    cur.execute("TRUNCATE activities, nearby_places, rooms, hotels RESTART IDENTITY CASCADE;")

    n_hotel = n_room = n_near = n_act = 0
    rooms_buf, near_buf, act_buf = [], [], []

    for fp in files:
        with open(fp, encoding="utf-8") as fh:
            d = json.load(fh)
        try:
            hid = int(d["hotel_id"])
        except (KeyError, ValueError, TypeError):
            print(f"  bỏ qua (thiếu hotel_id): {fp}")
            continue

        cur.execute(
            """INSERT INTO hotels
               (id,name,accommodation_type,star_rating,is_luxury,address,city,area,country,
                latitude,longitude,review_score,review_count,description,amenities,suitable_for,
                useful_info,reviews_detail,policy_notes,faq,images,source_url)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (id) DO NOTHING""",
            (
                hid, d.get("name"), d.get("accommodation_type"), to_float(d.get("star_rating")),
                bool(d.get("is_luxury")), d.get("address"), d.get("city"), d.get("area"), d.get("country"),
                to_float(d.get("latitude")), to_float(d.get("longitude")),
                to_float(d.get("review_score")), to_int(d.get("review_count")),
                d.get("description"), amenities_union(d), str_list(d.get("suitable_for")),
                Json(d.get("useful_info") or {}), Json(d.get("reviews_detail") or {}),
                policy_notes(d), Json(d.get("faq") or []),
                str_list(d.get("images") or d.get("image_urls")), d.get("source_url"),
            ),
        )
        n_hotel += 1

        for r in d.get("rooms") or []:
            bed = r.get("bed_type") or "; ".join(str_list(r.get("bed_types")))
            rooms_buf.append((
                hid, to_int(r.get("room_type_id")), r.get("name"),
                parse_price(r.get("price_per_night")), r.get("room_size"),
                to_int(r.get("max_occupancy")), bed or None, r.get("room_view"),
                str_list(r.get("room_amenities")), str_list(r.get("images")),
                to_float(r.get("review_score")),
            ))
        for i, p in enumerate(d.get("nearby_places") or []):
            near_buf.append((hid, i, p.get("name"), p.get("type"), to_float(p.get("distance_km"))))
        for a in d.get("activities") or []:
            act_buf.append((
                hid, to_int(a.get("activity_id")), a.get("title"), a.get("description"),
                parse_price(a.get("price")), to_float(a.get("review_score")),
            ))

    # 2. batch insert children
    if rooms_buf:
        execute_values(cur,
            "INSERT INTO rooms (hotel_id,room_type_id,name,price,room_size,max_occupancy,"
            "bed_type,room_view,room_amenities,images,review_score) VALUES %s", rooms_buf)
        n_room = len(rooms_buf)
    if near_buf:
        execute_values(cur,
            "INSERT INTO nearby_places (hotel_id,seq,name,type,distance_km) VALUES %s", near_buf)
        n_near = len(near_buf)
    if act_buf:
        execute_values(cur,
            "INSERT INTO activities (hotel_id,activity_id,title,description,price_amount,review_score) "
            "VALUES %s", act_buf)
        n_act = len(act_buf)

    conn.commit()
    cur.close()
    conn.close()
    print(f"✓ Ingest xong: {n_hotel} hotels, {n_room} rooms, {n_near} nearby_places, {n_act} activities")


if __name__ == "__main__":
    run()
