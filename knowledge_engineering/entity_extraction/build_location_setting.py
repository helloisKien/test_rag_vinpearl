"""build_location_setting.py — Suy SETTING của location TỪ DATA (Lớp A). Cách A.

Owner: Trương Anh Long (KE, DA10). Vấn đề: data location chỉ có country/city/area/lat/lng,
KHÔNG nói "Nha Trang là thành phố biển". Nhưng HOTEL TRONG location đó CÓ tín hiệu:
đa số hotel Nha Trang có AMEN_BEACHFRONT/SEA_VIEW -> suy Nha Trang = SETTING_COASTAL.

=> Suy location->SETTING bằng CO-OCCURRENCE (giống build_expansion), KHÔNG gõ tay địa lý:
   với mỗi city: % hotel mang tín hiệu coastal/mountain/island. Vượt ngưỡng -> gán SETTING.

Output: ontology/core/location_setting.generated.yaml — map LOC_id -> [SETTING_*] + bằng chứng %.
build_objects đọc file này để gắn SETTING cho hotel theo location (Bước 4).

Ngưỡng: coastal>=50%, mountain>=30%, island>=50%; tối thiểu MIN_HOTELS hotel (đủ mẫu).

Chạy: .venv/Scripts/python.exe -X utf8 -m knowledge_engineering.entity_extraction.build_location_setting
"""

from __future__ import annotations

import glob
import json
from collections import Counter, defaultdict

import yaml

HOTELS_GLOB = "data/cleaned/hotel_*.json"
TAGS_JSON = "knowledge_engineering/enrichment/hotel_tags.json"
LOC_YAML = "ontology/core/location.generated.yaml"
OUT_YAML = "ontology/core/location_setting.generated.yaml"

MIN_HOTELS = 5
TH = {"SETTING_COASTAL": 0.50, "SETTING_MOUNTAIN": 0.30, "SETTING_ISLAND": 0.50}

# tín hiệu (concept trong hotel_tags) -> setting của location
SIGNAL = {
    "SETTING_COASTAL": {"AMEN_BEACHFRONT", "AMEN_SEA_VIEW"},
    "SETTING_MOUNTAIN": {"SETTING_MOUNTAIN"},
    "SETTING_ISLAND": {"SETTING_ISLAND"},
}


def _city_to_loc() -> dict:
    """(city text) -> LOC concept id, từ location.generated (kind=place, là city/province)."""
    d = yaml.safe_load(open(LOC_YAML, encoding="utf-8"))["concepts"]
    from knowledge_engineering.common.normalize import normalize
    idx = {}
    for cid, v in d.items():
        if v.get("kind") == "place":
            lab = (v.get("label") or {}).get("vi", "")
            if lab:
                idx[normalize(lab, fold=True)] = cid
    return idx


def build() -> dict:
    from knowledge_engineering.common.normalize import normalize
    tags = json.load(open(TAGS_JSON, encoding="utf-8"))
    loc_idx = _city_to_loc()

    # hotel -> city; gom tín hiệu theo city
    total = Counter()
    sig: dict[str, Counter] = defaultdict(Counter)
    city_concepts: dict[str, list] = {}
    for f in glob.glob(HOTELS_GLOB):
        d = json.load(open(f, encoding="utf-8"))
        ci = d.get("city")
        if not ci:
            continue
        hid = f"acc_{d.get('hotel_id')}"
        cs = {t["concept"] for t in tags.get(hid, [])}
        total[ci] += 1
        for setting, signals in SIGNAL.items():
            if cs & signals:
                sig[ci][setting] += 1

    out: dict[str, dict] = {}
    for ci, n in total.items():
        if n < MIN_HOTELS:
            continue
        loc_id = loc_idx.get(normalize(ci, fold=True))
        if not loc_id:
            continue
        settings = {}
        for setting, th in TH.items():
            c = sig[ci][setting]
            if c / n >= th:
                settings[setting] = {"pct": round(100 * c / n), "n": n}
        if settings:
            out[loc_id] = settings
    return out


def write() -> int:
    data = build()
    header = (
        "# AUTO-GENERATED — KHÔNG sửa tay. Sinh bởi "
        "knowledge_engineering/entity_extraction/build_location_setting.py\n"
        "# Suy SETTING của location TỪ DATA: % hotel trong location có tín hiệu coastal/mountain/island.\n"
        "# KHÔNG gõ tay địa lý. build_objects đọc file này gắn SETTING cho hotel theo location.\n"
        "# Đổi corpus -> chạy lại. evidence = % hotel mang tín hiệu + cỡ mẫu.\n"
    )
    rows = {lid: {s: f"{v['pct']}% of {v['n']} hotel" for s, v in settings.items()}
            for lid, settings in sorted(data.items())}
    with open(OUT_YAML, "w", encoding="utf-8") as fh:
        fh.write(header)
        yaml.safe_dump({"version": "1.0.0", "location_setting": rows},
                       fh, allow_unicode=True, sort_keys=False)
    return len(data)


if __name__ == "__main__":
    n = write()
    data = build()
    print(f"Đã suy SETTING cho {n} location -> {OUT_YAML}")
    for lid, settings in sorted(data.items()):
        parts = [f"{s}({v['pct']}%)" for s, v in settings.items()]
        print(f"  {lid:28s} {', '.join(parts)}")
