"""Sinh quan hệ `near` (hotel <-> landmark) cho ontology — Task 1.5, Sprint 1.

LỚP A (tự sinh từ data): khi corpus mở rộng (27 -> 51 -> 500-1000 hotel) chỉ cần chạy lại
script này, KHÔNG gõ tay quan hệ near. Đầu vào: nearby_places (có distance_km) của mỗi hotel.
Đầu ra: dict relations để ghép vào ontology.yaml.

Cách hoạt động:
  - Đọc các landmark LMK_* trong ontology/core/location.generated.yaml (tự sinh) + location.yaml
    (curated, nếu có) — label + surface_forms.
  - Với mỗi nearby_places.name của từng hotel, khớp THEO CỤM TỪ (word-boundary, độ dài >= 5)
    để tránh false match kiểu "Ao" ⊂ "Bảo Đại".
  - Một hotel có thể trùng nhiều tên cho cùng landmark -> giữ distance_km NHỎ NHẤT.

Chạy: .venv/Scripts/python.exe -m knowledge_engineering.entity_extraction.build_relations
"""

import glob
import json
import re

import yaml

HOTELS_GLOB = "data/raw/hotels/*.json"
# Landmark giờ tự sinh ở location.generated.yaml; location.yaml chỉ còn alias curated (nếu có).
LOCATION_YAMLS = ["ontology/core/location.generated.yaml", "ontology/core/location.yaml"]
OUT_YAML = "ontology/relations_near.generated.yaml"  # LỚP A: file generated, regenerate an toàn
MIN_FORM_LEN = 5  # cụm match tối thiểu, tránh khớp từ ngắn mơ hồ


def load_landmark_forms(location_yamls: list = LOCATION_YAMLS) -> dict:
    """LMK concept_id -> list các cụm (label + surface_forms, lowercase), dài trước.
    Gộp từ nhiều file (generated + curated); curated override generated nếu trùng id."""
    out = {}
    for path in location_yamls:
        loc = (yaml.safe_load(open(path, encoding="utf-8")) or {}).get("concepts") or {}
        for cid, v in loc.items():
            if v.get("kind") != "landmark":
                continue
            forms = set()
            lb = v.get("label", {})
            for x in (lb.get("vi"), lb.get("en")):
                if x:
                    forms.add(x.lower())
            for lang in ("vi", "en"):
                for s in v.get("surface_forms", {}).get(lang, []) or []:
                    forms.add(s.lower())
            out[cid] = sorted(forms, key=len, reverse=True)
    return out


def match_landmark(name: str, exact_index: dict) -> str | None:
    """#5b: khớp CHẶT — tên nearby (chuẩn hóa) phải BẰNG ĐÚNG một form landmark, KHÔNG nhận cụm con.
    Tránh false-match 'Bệnh viện Bãi Cháy'->Bãi Cháy, 'Ngọc trai Long Beach'->Long Beach.
    exact_index: form(lower,strip) -> cid (dựng sẵn từ load_landmark_forms)."""
    return exact_index.get(name.lower().strip())


def build_near_relations(hotels_glob: str = HOTELS_GLOB) -> list[dict]:
    """Trả list relation: {from: acc_<hotel_id>, rel: near, to: LMK_*, distance_km: x}."""
    landmark_forms = load_landmark_forms()
    # dựng exact_index: form (lower,strip) -> cid. Form dài trước (nếu trùng form thì cid dài giữ sau).
    exact_index = {}
    for cid, forms in landmark_forms.items():
        for f in forms:
            exact_index[f.strip()] = cid
    near = {}  # (hotel_id, cid) -> min distance_km
    for f in sorted(glob.glob(hotels_glob)):
        d = json.load(open(f, encoding="utf-8"))
        hid = d.get("hotel_id")
        for p in d.get("nearby_places") or []:
            cid = match_landmark(p.get("name", ""), exact_index)
            if cid is None:
                continue
            km = p.get("distance_km")
            if km is None:
                continue
            key = (hid, cid)
            if key not in near or km < near[key]:
                near[key] = km
    rels = [
        {"from": f"acc_{hid}", "rel": "near", "to": cid, "distance_km": km}
        for (hid, cid), km in sorted(near.items())
    ]
    return rels


def write_generated(out_yaml: str = OUT_YAML) -> int:
    """Ghi quan hệ near ra file generated. Trả số quan hệ."""
    rels = build_near_relations()
    header = (
        "# AUTO-GENERATED — KHÔNG sửa tay. Sinh bởi "
        "knowledge_engineering/entity_extraction/build_relations.py\n"
        "# Nguồn: data/raw/hotels/*.json (nearby_places.distance_km). "
        "Regenerate khi corpus đổi.\n"
    )
    with open(out_yaml, "w", encoding="utf-8") as fh:
        fh.write(header)
        yaml.safe_dump(
            {"relations": rels}, fh, allow_unicode=True, sort_keys=False
        )
    return len(rels)


if __name__ == "__main__":
    n = write_generated()
    print(f"Đã ghi {n} quan hệ near -> {OUT_YAML}")
