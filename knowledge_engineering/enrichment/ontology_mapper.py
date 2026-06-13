"""ontology_mapper.py — Tagger lai gắn concept_id lên hotel (Sprint 2, Task 2.1).

Owner: Trương Anh Long (KE, DA10). Đọc data clean -> gắn concept HARD cho mỗi hotel.

KIẾN TRÚC CASCADE (rẻ -> đắt), mỗi tag có confidence + sources:
    Tầng 0  source-tag  : map field structured (amenities/suitable_for/view_types/
                          accommodation_type) qua ontology/source_tag_map.yaml. conf 0.95.
    Tầng 1  rule        : quét text (description/highlights/location_tags) qua
                          synonym_dictionary, XỬ LÝ PHỦ ĐỊNH ("không có hồ bơi"). conf 0.90.
    Tầng 2  embedding   : (MODEL-THAM-SỐ, CHƯA BẬT) cosine text vs anchor concept. Bật khi
                          team chốt model — xem `EmbeddingTagger`. conf = f(sim).
    Tầng 3  LLM         : (CHƯA BẬT) ca khó/mâu thuẫn. conf từ LLM.
    Fuse                : gom 1 tag/concept; nhiều tầng đồng thuận -> +conf; ghi mọi source.

PHẠM VI HIỆN TẠI: Tầng 0 + 1 (HARD facts). Tầng 2/3 để khung, chạy sau.
  -> Đủ phủ ~99% hotel cho amenity/object_type/purpose/setting (xem step1 report).
SOFT facts (style/aspect từ review) KHÔNG ở đây — thuộc Bước 5 (absa/profile).

Chạy: .venv/Scripts/python.exe -X utf8 -m knowledge_engineering.enrichment.ontology_mapper
"""

from __future__ import annotations

import glob
import json
from collections import defaultdict
from dataclasses import dataclass, field

import yaml

from knowledge_engineering.common.normalize import normalize

# ---------------------------------------------------------------------------
# Cấu hình
# ---------------------------------------------------------------------------
HOTELS_GLOB = "data/cleaned/hotel_*.json"
SOURCE_TAG_MAP = "ontology/source_tag_map.yaml"
SYNONYM_DICT = "ontology/synonym_dictionary.yaml"
CORE_GLOB = "ontology/core/*.yaml"
OUT_JSON = "knowledge_engineering/enrichment/hotel_tags.json"

CONF_SOURCE_TAG = 0.95
CONF_RULE = 0.90
CONF_MULTI_BONUS = 0.05  # cộng khi >=2 tầng đồng thuận (cap 1.0)

# Field text để Tầng 1 quét rule. (KHÔNG quét `description` đầy đủ ở bản này — dài + nhiễu
# marketing; chỉ quét field cô đọng. description full để Tầng 2 embedding xử lý sau.)
# Bỏ `location_tags` khỏi rule: nó lẫn tên địa danh/landmark -> rule đoán nhầm LOC_*; location
# của hotel ĐÃ có từ field area/city (Sprint 1), không đoán lại từ text.
RULE_TEXT_FIELDS = ["description_short", "highlights", "tags"]

# Tầng 1 (rule trên text) CHỈ được gắn facet sinh được PRESENCE từ structured/text khẳng định.
# Loại:
#   - aspect : SOFT thuần, chỉ dùng cho ABSA review (Bước 5). Rule bắt "phòng"/"vị trí"/"ăn uống"
#              trong marketing = rác (hotel nào chả có phòng/vị trí).
#   - style  : cảm nhận khách -> chờ review (experience). Description là lời tự quảng cáo.
#   - location: đã có từ structured (area/city), không đoán từ text.
# purpose: ĐƯỢC PHÉP — nhưng tag ở đây là `nature=presence` (từ suitable_for/khẳng định),
#   KHÁC với experience từ review. Mô hình hybrid: presence hard-dùng-được, experience soft.
# setting: LOẠI khỏi rule — text marketing "gần trung tâm"/"cách trung tâm 5km" làm SETTING_CITY_CENTER
#   over-tag (520/520 hotel = rác). Setting chỉ lấy từ Tầng 0 source-tag (view_types) + location
#   structured (Sprint 1 suy SETTING từ địa hình). KHÔNG đoán setting từ text tự do.
# object_type: LOẠI khỏi rule — facet `one`, nguồn chuẩn là accommodation_type (Tầng 0). Text mô tả
#   chứa "villa"/"khách sạn" làm rule gán object_type THỨ HAI (vd hotel + villa) -> vi phạm cardinality
#   one. Object_type chỉ lấy từ source-tag (đúng 1 giá trị Agoda khẳng định).
RULE_ALLOWED_FACETS = {"amenity", "purpose", "price_tier"}

# Manh mối phủ định tiếng Việt (dạng đã normalize, có dấu). Nếu xuất hiện ngay TRƯỚC surface
# form trong cửa sổ N token -> bỏ tag (vd "không có hồ bơi").
NEGATION_CUES = ["không", "ko", "chưa", "không có", "ko có", "thiếu"]
NEGATION_WINDOW = 3  # số token


# ---------------------------------------------------------------------------
# Nạp tài nguyên ontology
# ---------------------------------------------------------------------------
def load_concept_facets(core_glob: str = CORE_GLOB) -> dict[str, str]:
    """concept_id -> facet (để biết cardinality khi fuse + phân nhóm output)."""
    out: dict[str, str] = {}
    for f in sorted(glob.glob(core_glob)):
        d = yaml.safe_load(open(f, encoding="utf-8")) or {}
        for cid, v in (d.get("concepts") or {}).items():
            out[cid] = v.get("facet", "")
    return out


def load_source_tag_map(path: str = SOURCE_TAG_MAP) -> dict:
    return yaml.safe_load(open(path, encoding="utf-8")) or {}


def load_synonyms(path: str = SYNONYM_DICT) -> dict[str, list[str]]:
    d = yaml.safe_load(open(path, encoding="utf-8")) or {}
    return d.get("synonyms", {}) or {}


# ---------------------------------------------------------------------------
# Tag đơn vị
# ---------------------------------------------------------------------------
@dataclass
class Tag:
    concept: str
    confidence: float
    source: str  # "source_tag" | "rule" | "embedding" | "llm"
    evidence: str = ""
    # nature: bản chất bằng chứng (mô hình HYBRID — quyết định 2026-06-08).
    #   "presence"  : sự hiện diện khẳng định từ STRUCTURED (suitable_for/amenities/...). Tin cao,
    #                 KHÔNG cần sentiment. Dùng được như hard filter dù concept đánh fact_type=soft.
    #   "experience": cảm nhận từ REVIEW (Bước 5 ABSA). Soft, KÈM sentiment.
    # Tầng 0/1 ở đây chỉ sinh presence. Bước 5 sinh experience.
    nature: str = "presence"


# ---------------------------------------------------------------------------
# Tầng 0 — source-tag
# ---------------------------------------------------------------------------
def tag_source(hotel: dict, stmap: dict) -> list[Tag]:
    """Map field structured qua source_tag_map. Gộp amenities + amenity_groups."""
    tags: list[Tag] = []

    def emit(value: str, cid: str, field_name: str) -> None:
        tags.append(Tag(cid, CONF_SOURCE_TAG, "source_tag", f"{field_name}:{value}"))

    # accommodation_type (one)
    acc = hotel.get("accommodation_type")
    if isinstance(acc, str):
        cid = (stmap.get("accommodation_type") or {}).get(acc)
        if cid:
            emit(acc, cid, "accommodation_type")

    # suitable_for (many)
    for v in hotel.get("suitable_for", []) or []:
        cid = (stmap.get("suitable_for") or {}).get(v)
        if cid:
            emit(v, cid, "suitable_for")

    # view_types (many)
    for v in hotel.get("view_types", []) or []:
        cid = (stmap.get("view_types") or {}).get(v)
        if cid:
            emit(v, cid, "view_types")

    # amenities (flat) + amenity_groups[*] (many)
    amen_map = stmap.get("amenities") or {}
    amen_values = list(hotel.get("amenities", []) or [])
    for group in (hotel.get("amenity_groups") or {}).values():
        amen_values.extend(group or [])
    for v in amen_values:
        if isinstance(v, str):
            cid = amen_map.get(v)
            if cid:
                emit(v, cid, "amenity")

    return tags


# ---------------------------------------------------------------------------
# Tầng 1 — rule (synonym + phủ định)
# ---------------------------------------------------------------------------
def _has_negation_before(norm_text: str, surface: str, window: int = NEGATION_WINDOW) -> bool:
    """Có manh mối phủ định trong `window` token NGAY TRƯỚC surface form không?"""
    idx = norm_text.find(surface)
    if idx < 0:
        return False
    prefix = norm_text[:idx].strip().split()
    tail = prefix[-window:] if window else prefix
    return any(cue in tail for cue in NEGATION_CUES)


def _gather_rule_text(hotel: dict) -> str:
    parts: list[str] = []
    for fld in RULE_TEXT_FIELDS:
        v = hotel.get(fld)
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, list):
            parts.extend(x for x in v if isinstance(x, str))
    return " . ".join(parts)


def tag_rule(
    hotel: dict, synonyms: dict[str, list[str]], facets: dict[str, str]
) -> list[Tag]:
    """Quét text cô đọng qua synonym_dictionary; bỏ tag bị phủ định.

    Synonym key đã normalize (cả 2 dạng). Ở đây normalize text rồi tìm substring;
    chỉ nhận form >= 3 ký tự để tránh nhiễu (theo cảnh báo bàn giao Anh Tài).
    CHỈ giữ concept thuộc RULE_ALLOWED_FACETS (loại aspect/style/location khỏi rule).
    """
    text = _gather_rule_text(hotel)
    if not text:
        return []
    norm = normalize(text)  # dạng có dấu, đã tách từ
    tags: list[Tag] = []
    for form, cids in synonyms.items():
        if len(form) < 3:
            continue
        if form in norm:
            if _has_negation_before(norm, form):
                continue
            for cid in cids:
                if facets.get(cid) in RULE_ALLOWED_FACETS:
                    tags.append(Tag(cid, CONF_RULE, "rule", f"text:{form}"))
    return tags


# ---------------------------------------------------------------------------
# Tầng 2 — embedding (MODEL-THAM-SỐ, CHƯA BẬT)
# ---------------------------------------------------------------------------
class EmbeddingTagger:
    """Khung Tầng 2. KHÔNG hard-code model — nhận `model_name` + `threshold` từ config.

    Khi team chốt model embedding (bge-m3 / PhoBERT / e5...):
      1. khởi tạo: EmbeddingTagger(model_name=..., threshold=...)
      2. build_anchors() dựng vector đại diện từ description/label concept (regenerate khi đổi model)
      3. tag(text) trả Tag với conf = f(cosine)
    Đổi model = đổi `model_name` + chạy lại + re-calibrate `threshold`, KHÔNG sửa logic mapper.
    """

    def __init__(self, model_name: str | None = None, threshold: float = 0.55):
        self.model_name = model_name
        self.threshold = threshold
        self.enabled = False  # bật khi model sẵn sàng

    def build_anchors(self, concepts: dict) -> None:  # pragma: no cover - chưa bật
        raise NotImplementedError(
            "Tầng 2 chờ team chốt model embedding. Xem docstring + sprint2 plan."
        )

    def tag(self, text: str) -> list[Tag]:  # pragma: no cover - chưa bật
        if not self.enabled:
            return []
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Fuse
# ---------------------------------------------------------------------------
def fuse(all_tags: list[Tag]) -> list[dict]:
    """Gom 1 tag/concept. Nhiều tầng đồng thuận -> +conf. Ghi mọi source + evidence."""
    by: dict[str, list[Tag]] = defaultdict(list)
    for t in all_tags:
        by[t.concept].append(t)
    out: list[dict] = []
    for cid, hits in by.items():
        sources = sorted({h.source for h in hits})
        conf = max(h.confidence for h in hits)
        if len(sources) >= 2:
            conf = min(1.0, conf + CONF_MULTI_BONUS)
        # nature: presence thắng experience (presence là khẳng định từ structured).
        natures = {h.nature for h in hits}
        nature = "presence" if "presence" in natures else "experience"
        out.append(
            {
                "concept": cid,
                "confidence": round(conf, 2),
                "nature": nature,
                "sources": sources,
                "evidence": sorted({h.evidence for h in hits})[:5],
            }
        )
    return sorted(out, key=lambda x: (-x["confidence"], x["concept"]))


# ---------------------------------------------------------------------------
# Map 1 hotel
# ---------------------------------------------------------------------------
def map_hotel(
    hotel: dict, stmap: dict, synonyms: dict[str, list[str]], facets: dict[str, str]
) -> list[dict]:
    tags = tag_source(hotel, stmap) + tag_rule(hotel, synonyms, facets)
    # Tầng 2/3 thêm vào `tags` ở đây khi bật.
    return fuse(tags)


# ---------------------------------------------------------------------------
# Chạy toàn corpus
# ---------------------------------------------------------------------------
@dataclass
class RunStats:
    n_hotels: int = 0
    n_with_tag: int = 0
    per_concept: dict = field(default_factory=lambda: defaultdict(int))
    per_facet: dict = field(default_factory=lambda: defaultdict(int))


def run(hotels_glob: str = HOTELS_GLOB, out_json: str = OUT_JSON) -> RunStats:
    stmap = load_source_tag_map()
    synonyms = load_synonyms()
    facets = load_concept_facets()
    stats = RunStats()
    result: dict[str, list[dict]] = {}

    for f in sorted(glob.glob(hotels_glob)):
        hotel = json.load(open(f, encoding="utf-8"))
        hid = hotel.get("hotel_id")
        tags = map_hotel(hotel, stmap, synonyms, facets)
        result[f"acc_{hid}"] = tags
        stats.n_hotels += 1
        if tags:
            stats.n_with_tag += 1
        for t in tags:
            stats.per_concept[t["concept"]] += 1
            stats.per_facet[facets.get(t["concept"], "?")] += 1

    json.dump(result, open(out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return stats


if __name__ == "__main__":
    s = run()
    print(f"Hotels: {s.n_hotels} | có >=1 tag: {s.n_with_tag} "
          f"({100 * s.n_with_tag / s.n_hotels:.1f}%)")
    print("Tag theo facet:")
    for fct, n in sorted(s.per_facet.items(), key=lambda x: -x[1]):
        print(f"  {fct:14s} {n}")
    print(f"-> {OUT_JSON}")
