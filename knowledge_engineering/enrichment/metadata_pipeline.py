"""metadata_pipeline.py — Map / validate / reconcile metadata (Sprint 2, Task 2.3).

Owner: Trương Anh Long (KE, DA10). Với data crawl GIÀU (Agoda), đây KHÔNG phải "trích xuất
từ text thô" mà là: MAP trường crawl -> schema KE; ĐỐI CHIẾU mâu thuẫn; điền range_filters
+ location + nearby_places. Kết hợp với tag (Bước 2) để ra phần HARD của knowledge_object.

3 việc chính:
  1. MAP      : country/province/city/area + lat/long -> khối location; rooms[].price_per_night
                -> price_min; star/review_score -> range_filters.
  2. RECONCILE: SUY price_tier KHÔNG tin cờ `is_luxury` mù (101/520 hotel star>=5 nhưng
                is_luxury=False — Agoda gắn cờ không nhất quán). Gộp star + gold_circle + giá.
  3. VALIDATE : (ở build object — Bước 4) pydantic schema.py bắt concept sai / thiếu field.

KHÔNG sinh ở đây: concept tag (Bước 2 đã làm), SOFT/review (Bước 5).

Chạy: .venv/Scripts/python.exe -X utf8 -m knowledge_engineering.enrichment.metadata_pipeline
"""

from __future__ import annotations

import glob
import json
from dataclasses import dataclass, field

HOTELS_GLOB = "data/cleaned/hotel_*.json"
OUT_JSON = "knowledge_engineering/enrichment/hotel_metadata.json"

# Map accommodation_type -> type chữ thường cho knowledge_object.type (khác concept OBJ_*).
TYPE_SLUG = {
    "Khách sạn": "hotel", "Resort": "resort", "Căn hộ": "apartment",
    "Căn hộ dịch vụ": "apartment", "Nhà dân": "homestay", "Toàn bộ căn nhà": "homestay",
    "Nhà khách / Nhà nghỉ B&B": "bnb", "Giường và Bữa sáng": "bnb", "Nhà nghỉ": "guesthouse",
    "Nhà nghỉ ven đường": "guesthouse", "Biệt thự": "villa", "Biệt thự nghỉ dưỡng": "villa",
    "Bungalow": "bungalow",
}


# ---------------------------------------------------------------------------
# (1) MAP — location + range_filters
# ---------------------------------------------------------------------------
def map_location(hotel: dict) -> dict:
    """Khối location từ field structured (đã clean ở Sprint 1). Giữ text + toạ độ."""
    return {
        "country": hotel.get("country"),
        "province": hotel.get("province"),
        "city": hotel.get("city"),
        "district": hotel.get("district"),
        "area": hotel.get("area"),
        "lat": hotel.get("latitude"),
        "lng": hotel.get("longitude"),
    }


def price_min(hotel: dict) -> int | None:
    """Giá thấp nhất từ rooms[].price_per_night (room_grid.cheapest_price rỗng toàn corpus)."""
    prices = [
        r.get("price_per_night")
        for r in (hotel.get("rooms") or [])
        if isinstance(r.get("price_per_night"), (int, float)) and r.get("price_per_night") > 0
    ]
    return int(min(prices)) if prices else None


def map_range_filters(hotel: dict) -> dict:
    """Attribute SỐ (filter khoảng) — KHÔNG phải concept. star 0.0 = chưa xếp hạng -> None."""
    star = hotel.get("star_rating")
    star = None if (star in (None, 0, 0.0)) else float(star)
    rf = {
        "star_rating": star,
        "review_score": hotel.get("review_score"),
        "price_min_vnd": price_min(hotel),
    }
    return {k: v for k, v in rf.items() if v is not None}


# ---------------------------------------------------------------------------
# (1b) MAP — nearby_places (đọc key `type`, KHÔNG phải `category` — Bước 0)
# ---------------------------------------------------------------------------
def map_nearby(hotel: dict, limit: int = 10) -> list[dict]:
    out = []
    for p in hotel.get("nearby_places", []) or []:
        if not isinstance(p, dict):
            continue
        out.append({
            "name": p.get("name"),
            "category": p.get("type"),          # nguồn dùng key `type`
            "distance_km": p.get("distance_km"),
        })
    out.sort(key=lambda x: (x["distance_km"] is None, x["distance_km"] or 0))
    return out[:limit]


# ---------------------------------------------------------------------------
# (2) RECONCILE — suy price_tier (KHÔNG tin is_luxury mù)
# ---------------------------------------------------------------------------
def infer_price_tier(hotel: dict) -> tuple[str | None, str]:
    """Suy PRICE_* từ NHIỀU tín hiệu. Trả (concept_id | None, ghi_chú_reconcile).

    Logic (ưu tiên bằng chứng cứng, không tin cờ is_luxury đơn lẻ):
      - Gold Circle award (Agoda chỉ trao cho property chất lượng cao) HOẶC is_luxury=True
        + star>=5  -> PRICE_LUXURY.
      - star>=5 (kể cả is_luxury=False)              -> PRICE_UPSCALE (5 sao nhưng chưa đủ tín
                                                        hiệu luxury; tránh thổi mọi 5 sao thành luxury).
      - star 4..4.5                                  -> PRICE_UPSCALE.
      - star 3..3.5                                  -> PRICE_MID.
      - star <3                                      -> PRICE_BUDGET.
      - star None (chưa xếp hạng)                    -> None (để filter giá/score lo).
    Ghi chú reconcile khi nguồn mâu thuẫn (vd star>=5 nhưng is_luxury=False).
    """
    star = hotel.get("star_rating")
    star = None if (star in (None, 0, 0.0)) else float(star)
    lux = hotel.get("is_luxury") is True
    gold = bool(hotel.get("gold_circle_award_year"))
    note = ""

    if star is None:
        return None, "star=0/None (chưa xếp hạng) -> không suy tier; dựa range_filter giá"

    if star >= 5 and (gold or lux):
        tier = "PRICE_LUXURY"
    elif star >= 5:
        tier = "PRICE_UPSCALE"
        note = "star>=5 nhưng không gold/luxury -> UPSCALE (không thổi 5 sao thành luxury)"
    elif star >= 4:
        tier = "PRICE_UPSCALE"
    elif star >= 3:
        tier = "PRICE_MID"
    else:
        tier = "PRICE_BUDGET"

    # cờ mâu thuẫn để audit (đừng tin is_luxury mù)
    if star >= 5 and hotel.get("is_luxury") is False and gold:
        note = (note + " | ") if note else ""
        note += "MÂU THUẪN: is_luxury=False nhưng 5 sao + Gold Circle -> tin star+gold"
    return tier, note


# ---------------------------------------------------------------------------
# Map 1 hotel
# ---------------------------------------------------------------------------
def build_metadata(hotel: dict) -> dict:
    tier, note = infer_price_tier(hotel)
    return {
        "type": TYPE_SLUG.get(hotel.get("accommodation_type"), "hotel"),
        "location": map_location(hotel),
        "range_filters": map_range_filters(hotel),
        "price_tier": tier,
        "price_tier_note": note,
        "nearby_places": map_nearby(hotel),
    }


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
@dataclass
class Stats:
    n: int = 0
    tier_dist: dict = field(default_factory=dict)
    conflicts: int = 0
    no_price: int = 0
    no_star: int = 0


def run(hotels_glob: str = HOTELS_GLOB, out_json: str = OUT_JSON) -> Stats:
    st = Stats()
    result: dict[str, dict] = {}
    for f in sorted(glob.glob(hotels_glob)):
        hotel = json.load(open(f, encoding="utf-8"))
        hid = hotel.get("hotel_id")
        meta = build_metadata(hotel)
        result[f"acc_{hid}"] = meta
        st.n += 1
        t = meta["price_tier"]
        st.tier_dist[t] = st.tier_dist.get(t, 0) + 1
        if "MÂU THUẪN" in meta["price_tier_note"]:
            st.conflicts += 1
        if "price_min_vnd" not in meta["range_filters"]:
            st.no_price += 1
        if "star_rating" not in meta["range_filters"]:
            st.no_star += 1
    json.dump(result, open(out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return st


if __name__ == "__main__":
    s = run()
    print(f"Hotels: {s.n}")
    print(f"price_tier: {dict(sorted(s.tier_dist.items(), key=lambda x: str(x[0])))}")
    print(f"ca mâu thuẫn is_luxury (đã reconcile): {s.conflicts}")
    print(f"thiếu giá: {s.no_price} | chưa xếp sao: {s.no_star}")
    print(f"-> {OUT_JSON}")
