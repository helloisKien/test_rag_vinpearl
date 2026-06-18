"""DA10 — Phase 5: Rule-based intent parser (R8, R9, R10).

Trích từ query tiếng Việt:
  city, accommodation_type, star_rating, review_score, price,
  amenities, suitable_for (soft), keyword_expansion, concepts.

Nguồn: ontology/synonym_dictionary.yaml (surface → concept)
       ontology/core/location.generated.yaml (LOC_* label.vi → DB city).
Singleton: _state build lần đầu khi parse() được gọi, sau đó cache.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

# ── CONCEPT → DB STRING MAP ───────────────────────────────────────────────────

# AMEN_* → EXACT strings trong hotels.amenities (từ Agoda VN, xác nhận qua golden_set_v1).
# Chọn chuỗi đầu tiên làm primary; prefilter @> sẽ dùng chuỗi này.
_AMEN_DB: dict[str, list[str]] = {
    "AMEN_POOL":             ["Bể bơi ngoài trời", "Hồ bơi ngoài trời"],
    "AMEN_INFINITY_POOL":    ["Bể bơi vô cực", "Hồ bơi vô cực"],
    "AMEN_KIDS_POOL":        ["Bể bơi trẻ em", "Hồ bơi trẻ em"],
    "AMEN_PRIVATE_POOL":     ["Bể bơi riêng", "Hồ bơi riêng"],
    "AMEN_BEACHFRONT":       ["Bãi biển riêng"],
    "AMEN_SEA_VIEW":         ["Nhìn ra biển"],
    "AMEN_SPA":              ["Mát-xa", "Spa", "Spa xông khô"],
    "AMEN_GYM":              ["Phòng tập"],
    "AMEN_BAR":              ["Quán bar", "Bar"],
    "AMEN_RESTAURANT":       ["Nhà hàng"],
    "AMEN_CAFE":             ["Quán cà phê"],
    "AMEN_GARDEN":           ["Vườn"],
    "AMEN_WIFI":             ["WiFi miễn phí", "Wi-Fi miễn phí"],
    "AMEN_PARKING":          ["Đỗ xe miễn phí", "Đỗ xe tại chỗ", "Bãi đỗ xe miễn phí"],
    "AMEN_AC":               ["Điều hòa"],
    "AMEN_KITCHEN":          ["Bếp"],
    "AMEN_MEETING_ROOM":     ["Phòng họp"],
    "AMEN_AIRPORT_SHUTTLE":  ["Dịch vụ đưa đón sân bay"],
    "AMEN_ELEVATOR":         ["Thang máy"],
    "AMEN_WHEELCHAIR":       ["Tiện nghi dành cho người khuyết tật"],
    "AMEN_PET_FRIENDLY":     ["Cho phép mang thú cưng"],
    "AMEN_KIDS_CLUB":        ["CLB trẻ em", "Câu lạc bộ trẻ em", "Khu vui chơi trẻ em"],
    "AMEN_BABYSITTING":      ["Dịch vụ trông trẻ"],
    "AMEN_BIKE":             ["Cho thuê xe đạp"],
    "AMEN_GOLF":             ["Sân golf"],
    "AMEN_TENNIS":           ["Sân tennis"],
    "AMEN_WATERSPORT":       ["Thể thao dưới nước"],
    "AMEN_HIKING":           ["Đường đi bộ"],
    "AMEN_KARAOKE":          ["Karaoke"],
    "AMEN_GAME_ROOM":        ["Phòng trò chơi"],
    # R18: non-smoking concept-level (biến thể: "Hoàn toàn không hút thuốc" / "Phòng không hút thuốc")
    "AMEN_NON_SMOKING":      ["Hoàn toàn không hút thuốc", "Phòng không hút thuốc"],
    # Ngoài facets nhưng có trong golden_set:
    "AMEN_POOL_BAR":         ["Quán bar cạnh bể bơi"],
    "AMEN_PLAYGROUND":       ["Sân chơi"],
    "AMEN_WATERSPORTS":      ["Thể thao dưới nước"],
}

# OBJ_* → DB accommodation_type string (Agoda English)
_OBJ_DB: dict[str, str] = {
    "OBJ_HOTEL":      "Hotel",
    "OBJ_RESORT":     "Resort",
    "OBJ_VILLA":      "Villa",
    "OBJ_HOMESTAY":   "Homestay",
    "OBJ_APARTMENT":  "Apartment",
    "OBJ_GUESTHOUSE": "Guesthouse",
    "OBJ_BNB":        "Bed and Breakfast",
    "OBJ_BUNGALOW":   "Bungalow",
}

# PURPOSE_* → DB suitable_for strings (soft; thêm vào keyword_expansion, không hard-filter)
_PURPOSE_KW: dict[str, list[str]] = {
    "PURPOSE_FAMILY":   ["gia đình", "trẻ em", "con nhỏ"],
    "PURPOSE_ROMANTIC": ["cặp đôi", "lãng mạn", "tuần trăng mật"],
    "PURPOSE_BUSINESS": ["công tác", "hội nghị", "hội thảo"],
    "PURPOSE_SOLO":     ["một mình", "du lịch solo"],
    "PURPOSE_GROUP":    ["nhóm", "đoàn"],
    "PURPOSE_WELLNESS": ["nghỉ dưỡng", "spa", "thư giãn"],
}

# ── DATA CLASSES ──────────────────────────────────────────────────────────────


@dataclass
class ParsedIntent:
    city: str | None = None
    accommodation_type: list[str] = field(default_factory=list)
    star_rating: dict = field(default_factory=dict)
    review_score: dict = field(default_factory=dict)
    price: dict = field(default_factory=dict)
    amenities: list[str] = field(default_factory=list)
    suitable_for: list[str] = field(default_factory=list)
    keyword_expansion: list[str] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)
    parsed_by: str = "rule_based"
    confidence: float = 0.0

    def to_hard_filters(self) -> dict:
        """Format cho prefilter.sql_whitelist()."""
        f: dict = {}
        if self.city:
            f["city"] = self.city
        if self.accommodation_type:
            f["accommodation_type"] = self.accommodation_type
        if self.star_rating:
            f["star_rating"] = self.star_rating
        if self.review_score:
            f["review_score"] = self.review_score
        if self.price:
            f["price"] = self.price
        if self.amenities:
            f["amenities"] = self.amenities
        if self.suitable_for:
            f["suitable_for"] = self.suitable_for
        return f

    def expanded_query(self, original: str) -> str:
        """Nối query gốc với keyword_expansion để BM25 boost."""
        extra = [t for t in self.keyword_expansion if t.lower() not in original.lower()]
        if extra:
            return original + " " + " ".join(extra)
        return original


# ── EXTRA SURFACE FORMS (supplement synonym_dictionary cho các concept thiếu) ──
# Các surface form này KHÔNG có trong ontology/synonym_dictionary.yaml nhưng
# xuất hiện trong golden_set_v1 hoặc Agoda VN data. Thêm vào form_map khi load.
# Format: normalized_form (no diacritics, no underscore) → [concept_id]
_EXTRA_FORMS: dict[str, list[str]] = {
    # AMEN_POOL_BAR — "Quán bar cạnh bể bơi" (golden AMEN-002)
    "quan bar canh be boi":      ["AMEN_POOL_BAR"],
    "quan bar canh ho boi":      ["AMEN_POOL_BAR"],
    "pool bar":                  ["AMEN_POOL_BAR"],
    "bar ben ho boi":            ["AMEN_POOL_BAR"],
    "bar canh be boi":           ["AMEN_POOL_BAR"],
    # AMEN_NON_SMOKING — "Hoàn toàn không hút thuốc" (golden AMEN-009, R18)
    "hoan toan khong hut thuoc": ["AMEN_NON_SMOKING"],
    "phong khong hut thuoc":     ["AMEN_NON_SMOKING"],
    "khong hut thuoc":           ["AMEN_NON_SMOKING"],
    "non smoking":               ["AMEN_NON_SMOKING"],
    "non-smoking":               ["AMEN_NON_SMOKING"],
    # AMEN_PLAYGROUND — "Sân chơi" (golden AMEN-010)
    # 5-token form để consume toàn bộ cụm, tránh AMEN_KIDS_CLUB match "tre em"
    "san choi cho tre em":       ["AMEN_PLAYGROUND"],
    "san choi tre em":           ["AMEN_PLAYGROUND"],
    "san choi":                  ["AMEN_PLAYGROUND"],
    "playground":                ["AMEN_PLAYGROUND"],
}

# ── SINGLETON STATE ───────────────────────────────────────────────────────────

_state: dict | None = None


def _norm(text: str) -> str:
    """Lowercase + bỏ dấu tiếng Việt; thay _ bằng space."""
    text = text.replace("_", " ").lower()
    nfd = unicodedata.normalize("NFD", text)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def _is_city_concept(cid: str) -> bool:
    """True nếu là LOC_* thành phố/tỉnh (không phải area con, không phải landmark, không phải country)."""
    return (
        cid.startswith("LOC_")
        and "__" not in cid
        and cid != "LOC_VIETNAM"
    )


def _load() -> dict:
    global _state
    if _state is not None:
        return _state

    try:
        import yaml
    except ImportError:
        raise ImportError("pyyaml required: pip install pyyaml")

    root = Path(__file__).parent.parent

    # 1. Load synonym_dictionary.yaml
    syn_path = root / "ontology" / "synonym_dictionary.yaml"
    with open(syn_path, encoding="utf-8") as f:
        syn_data = yaml.safe_load(f)
    synonyms: dict[str, list[str]] = syn_data.get("synonyms", {})

    # 2. Load location.generated.yaml → concept_id → label_vi
    loc_path = root / "ontology" / "core" / "location.generated.yaml"
    with open(loc_path, encoding="utf-8") as f:
        loc_data = yaml.safe_load(f)
    loc_concepts: dict = loc_data.get("concepts", {})

    loc_label: dict[str, str] = {}  # concept_id → label.vi (for city filter)
    for cid, info in loc_concepts.items():
        if cid.startswith("LMK_"):
            continue
        lv = info.get("label", {}).get("vi", "")
        if lv:
            loc_label[cid] = lv

    # 3. Build normalized surface_form → [concept_id] lookup
    form_map: dict[str, list[str]] = {}

    def _add(form: str, cids: list[str]) -> None:
        nf = _norm(form)
        if not nf.strip():
            return
        if nf not in form_map:
            form_map[nf] = []
        for c in cids:
            if c not in form_map[nf]:
                form_map[nf].append(c)

    # From synonym_dictionary — bỏ các form quá ngắn (<3 chars) cho LMK_* (tránh
    # match số như "4", "2/4" → LMK_CONG_VIEN_16_4 / LMK_QUANG_TRUONG_2_4)
    for form, cids in synonyms.items():
        nf = _norm(str(form)).replace("_", " ").strip()
        if len(nf) < 3 and any(c.startswith("LMK_") for c in cids):
            continue  # bỏ form quá ngắn của landmark → tránh false positive số
        _add(str(form), cids)

    # From location.generated.yaml surface_forms (supplement gaps)
    for cid, info in loc_concepts.items():
        if cid.startswith("LMK_"):
            continue
        for f in info.get("surface_forms", {}).get("vi", []):
            _add(f, [cid])

    # Extra forms — OVERRIDE (không append) để concept cụ thể hơn thắng synonym_dict.
    # Ví dụ: "quan bar canh be boi" trong synonym_dict → AMEN_BAR, nhưng ta muốn → AMEN_POOL_BAR.
    for form, cids in _EXTRA_FORMS.items():
        nf = _norm(form)
        if nf.strip():
            form_map[nf] = list(cids)  # ghi đè hoàn toàn

    # 4. Sort forms by token count then char length (longest / most-specific first)
    sorted_forms = sorted(
        form_map.keys(),
        key=lambda x: (-len(x.split()), -len(x))
    )

    _state = {
        "form_map": form_map,
        "sorted_forms": sorted_forms,
        "loc_label": loc_label,
    }
    return _state


# ── NUMERIC FILTER EXTRACTION ─────────────────────────────────────────────────

_STAR_PATTERNS = [
    # "5 sao", "4 sao trở lên", "từ 4 sao"
    (re.compile(r"t[ừu]\s+(\d)\s*sao", re.I), "min", int),
    (re.compile(r"(\d)\s*sao\s*(tr[ởo]+\s*l[eê]n)?", re.I), "min", int),
]

_REVIEW_PATTERNS = [
    # "điểm 8.5", "đánh giá trên 9", "review trên 8"
    (re.compile(r"(?:đ[aá]nh gi[aá]|điểm|review|rating)\s*tr[eê]n\s*([\d.]+)", re.I), "min", float),
    (re.compile(r"(?:đ[aá]nh gi[aá]|điểm)\s*([\d.]+)\s*(?:tr[ởo]+\s*l[eê]n)?", re.I), "min", float),
]

_PRICE_PATTERNS = [
    # "dưới 1 triệu", "dưới 500k", "dưới 2tr"
    (re.compile(r"d[ưu][ớo]i\s*([\d,.]+)\s*(tri[eệ]u|tr\b|k\b|000)", re.I), "max"),
    # "trên 500k", "trên 1 triệu"
    (re.compile(r"tr[eê]n\s*([\d,.]+)\s*(tri[eệ]u|tr\b|k\b|000)", re.I), "min"),
    # "dưới 500000"
    (re.compile(r"d[ưu][ớo]i\s*([\d]{4,})", re.I), "max"),
    (re.compile(r"tr[eê]n\s*([\d]{4,})", re.I), "min"),
]


def _parse_price_value(num_str: str, unit: str) -> float:
    num_str = num_str.replace(",", ".")
    val = float(num_str)
    u = unit.lower().strip(".")
    if u in ("trieu", "triệu", "tr"):
        val *= 1_000_000
    elif u in ("k",):
        val *= 1_000
    elif u == "000":
        val *= 1_000
    return val


def _extract_numeric(query: str) -> tuple[dict, dict, dict]:
    """Returns (star_rating, review_score, price) dicts."""
    star: dict = {}
    rv: dict = {}
    price: dict = {}

    for pat, key, cast in _STAR_PATTERNS:
        m = pat.search(query)
        if m:
            val = cast(m.group(1))
            if 1 <= val <= 5:
                star[key] = val
                break

    for pat, key, cast in _REVIEW_PATTERNS:
        m = pat.search(query)
        if m:
            rv[key] = cast(m.group(1))
            break

    for pat, key, *_ in _PRICE_PATTERNS:
        m = pat.search(query)
        if m:
            try:
                grps = m.groups()
                unit = grps[1] if len(grps) > 1 else ""
                price[key] = _parse_price_value(grps[0], unit)
            except Exception:
                pass
            break

    return star, rv, price


# ── CONCEPT EXTRACTION ────────────────────────────────────────────────────────


def _extract_concepts(query_norm: str) -> list[tuple[str, str]]:
    """Trả list (concept_id, matched_form) từ query đã normalize."""
    st = _load()
    form_map = st["form_map"]
    sorted_forms = st["sorted_forms"]

    tokens = query_norm.split()
    consumed = [False] * len(tokens)
    results: list[tuple[str, str]] = []

    for form in sorted_forms:
        form_tokens = form.split()
        n = len(form_tokens)
        for i in range(len(tokens) - n + 1):
            if any(consumed[i:i + n]):
                continue
            if tokens[i:i + n] == form_tokens:
                for cid in form_map[form]:
                    results.append((cid, form))
                for j in range(i, i + n):
                    consumed[j] = True
                break  # form matched, don't match again at different position

    return results


# ── MAIN PARSE FUNCTION ───────────────────────────────────────────────────────


def parse(query: str) -> ParsedIntent:
    """Parse query tiếng Việt → ParsedIntent.

    ParsedIntent.to_hard_filters() trả dict dùng trực tiếp trong prefilter.sql_whitelist().
    ParsedIntent.expanded_query(query) trả query mở rộng cho BM25.
    """
    st = _load()
    loc_label = st["loc_label"]

    intent = ParsedIntent()
    q_norm = _norm(query)

    # 1. Extract concept matches
    matches = _extract_concepts(q_norm)

    seen_concepts: set[str] = set()
    kw_set: set[str] = set()

    for cid, form in matches:
        if cid in seen_concepts:
            continue
        seen_concepts.add(cid)
        intent.concepts.append(cid)

        # City (top-level LOC_*, not area, not landmark)
        if _is_city_concept(cid) and intent.city is None:
            lv = loc_label.get(cid)
            if lv:
                intent.city = lv
                kw_set.add(lv)

        # Accommodation type — bỏ qua OBJ_HOTEL vì "khách sạn" là từ generic trong
        # tiếng Việt (không phải filter cứng "Hotel" type), chỉ filter loại đặc thù.
        elif cid in _OBJ_DB and cid != "OBJ_HOTEL":
            db_str = _OBJ_DB[cid]
            if db_str not in intent.accommodation_type:
                intent.accommodation_type.append(db_str)
            kw_set.add(db_str.lower())

        # Amenities
        elif cid in _AMEN_DB:
            primary = _AMEN_DB[cid][0]
            if primary not in intent.amenities:
                intent.amenities.append(primary)
            # Thêm synonyms làm keyword_expansion
            for s in _AMEN_DB[cid]:
                kw_set.add(s.lower())

        # Purpose (soft — keyword_expansion only, không hard-filter)
        elif cid in _PURPOSE_KW:
            for kw in _PURPOSE_KW[cid]:
                kw_set.add(kw)

        # SETTING_*, STYLE_*, PRICE_*, ASPECT_* → keyword_expansion
        else:
            kw_set.add(form.replace("_", " "))

    # 2. Numeric filters
    star, rv, price = _extract_numeric(query)
    if star:
        intent.star_rating = star
    if rv:
        intent.review_score = rv
    if price:
        intent.price = price

    # 3. Keyword expansion (loại bỏ trùng với query gốc đã normalize)
    q_lower = query.lower()
    intent.keyword_expansion = [
        kw for kw in sorted(kw_set)
        if kw and kw not in q_lower
    ]

    # 4. Confidence heuristic
    signals = (
        (1 if intent.city else 0)
        + (1 if intent.accommodation_type else 0)
        + (1 if intent.amenities else 0)
        + (0.5 if intent.star_rating else 0)
        + (0.5 if intent.review_score else 0)
        + (0.3 if intent.price else 0)
    )
    intent.confidence = round(min(signals / 3.0, 1.0), 2)

    return intent


# ── SMOKE TEST ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    SAMPLES = [
        # (query, expected_city, note)
        ("Tìm resort ở Đảo Phú Quốc có quán bar cạnh bể bơi",
         "Đảo Phú Quốc", "AMEN-002: city + amenity pool_bar + accom Resort"),
        ("Tìm khách sạn ở Nha Trang có bể bơi ngoài trời",
         "Nha Trang", "AMEN-001: city + amenity pool"),
        ("Tìm khách sạn ở Hà Nội có phòng tập gym",
         "Hà Nội", "AMEN-004: city + amenity gym"),
        ("Tìm khách sạn ở Hồ Chí Minh có nhà hàng trong khuôn viên",
         "Hồ Chí Minh", "AMEN-008: city + amenity restaurant"),
        ("Tìm khách sạn nằm ngay trong khu phố cổ Hội An",
         "Hội An", "DESC-003: city only (soft: phố cổ)"),
        ("Tìm khách sạn 5 sao ở Đà Nẵng có spa",
         "Đà Nẵng", "star_rating + city + amenity spa"),
        ("Tìm resort nghỉ dưỡng 4 sao trở lên giá dưới 2 triệu ở Vũng Tàu",
         "Vũng Tàu", "accom + star + price + city"),
        ("Tìm khách sạn ở Hà Nội phù hợp cho gia đình có trẻ em",
         "Hà Nội", "FAQ-007: city + purpose family (soft)"),
        ("Tìm khách sạn ở Hồ Chí Minh hoàn toàn không hút thuốc",
         "Hồ Chí Minh", "AMEN-009: city + amenity non-smoking"),
        ("Tìm khách sạn ở Nha Trang có sân chơi cho trẻ em",
         "Nha Trang", "AMEN-010: city + amenity playground"),
    ]

    print("=" * 72)
    print("DA10 Phase 5 — Intent Parser Smoke Test")
    print("=" * 72)

    ok = 0
    for query, exp_city, note in SAMPLES:
        intent = parse(query)
        city_ok = (intent.city == exp_city)
        status = "OK" if city_ok else "FAIL"
        if city_ok:
            ok += 1
        print(f"\n[{status}] {note}")
        print(f"  Query  : {query}")
        print(f"  City   : {intent.city!r:25s} (expected: {exp_city!r})")
        print(f"  Accom  : {intent.accommodation_type}")
        print(f"  Amenity: {intent.amenities}")
        print(f"  Star   : {intent.star_rating}  Review: {intent.review_score}  Price: {intent.price}")
        print(f"  Expand : {intent.keyword_expansion[:6]}")
        print(f"  Concept: {intent.concepts}")
        hf = intent.to_hard_filters()
        print(f"  Filters: {json.dumps(hf, ensure_ascii=False)}")

    print(f"\n{'='*72}")
    print(f"City extraction: {ok}/{len(SAMPLES)} OK")
    print(f"\nXONG. Gửi output này cho assistant để xác nhận Phase 5.")
