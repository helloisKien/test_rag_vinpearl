"""query_demo.py — CÔNG CỤ TEST TAY (KHÔNG phải search engine production).

Mục đích: kiểm CHẤT LƯỢNG NHÃN HARD đã gắn ở Bước 4. Mô phỏng phần "filter theo concept +
range" mà tầng search (Anh Tài/Đạt) sẽ làm — KHÔNG có vector/BM25/ranking.

Luồng (giống tầng search sẽ làm):
  câu hỏi tiếng Việt
   -> normalize + tra synonym_dictionary  => tập concept + facet
   -> bắt range filter đơn giản (dưới X triệu / trên X điểm / N sao)
   -> lọc knowledge_objects.json theo concept (AND) + range + location text
   -> in hotel khớp.

Chạy:  .venv/Scripts/python.exe -X utf8 -m knowledge_engineering.enrichment.query_demo "câu hỏi"
"""

from __future__ import annotations

import json
import re
import sys

import yaml

from knowledge_engineering.common.implicit_intent import parse_implicit_intent
from knowledge_engineering.common.normalize import normalize

# PURPOSE -> amenity "minh chứng" cho mục đích đó. Khi suy ra PURPOSE (từ surface form HOẶC
# intent ngầm), hotel có các amenity này được ƯU TIÊN lên top (không lọc cứng — soft fact).
# Khớp query_expansion.yaml (PURPOSE_FAMILY -> AMEN_KIDS_*).
PURPOSE_EVIDENCE = {
    "PURPOSE_FAMILY": {"AMEN_KIDS_CLUB", "AMEN_KIDS_POOL", "AMEN_BABYSITTING"},
    "PURPOSE_ROMANTIC": {"AMEN_SEA_VIEW", "AMEN_PRIVATE_POOL", "STYLE_ROMANTIC"},
    "PURPOSE_BUSINESS": {"AMEN_MEETING_ROOM", "AMEN_WIFI"},
    "PURPOSE_WELLNESS": {"AMEN_SPA", "STYLE_QUIET"},
    "PURPOSE_GROUP": {"AMEN_KARAOKE", "AMEN_GAME_ROOM", "AMEN_MEETING_ROOM"},
}

OBJ_JSON = "knowledge_engineering/enrichment/knowledge_objects.json"
SYN_YAML = "ontology/synonym_dictionary.yaml"

_objs = json.load(open(OBJ_JSON, encoding="utf-8"))
_syn = yaml.safe_load(open(SYN_YAML, encoding="utf-8"))["synonyms"]


# ---------------------------------------------------------------------------
# Parse câu hỏi -> concept + range + location
# ---------------------------------------------------------------------------
def parse_concepts(q: str) -> tuple[list[str], dict[str, str]]:
    """Suy concept từ câu bằng HAI cơ chế bổ sung nhau:

      1. LOOKUP surface form: tra mọi cụm con (1-4 từ) qua synonym_dictionary. Bắt cách nói
         CỐ ĐỊNH ("gia đình", "ven biển"...).
      2. PATTERN intent ngầm (implicit_intent): bắt MÔ TẢ HOÀN CẢNH có biến số mà lookup không
         kham nổi ("nhà tôi có 2 con" -> PURPOSE_FAMILY).

    Trả (sorted concept_ids, {concept_id: bằng-chứng}) — bằng chứng chỉ có cho concept từ
    cơ chế 2 (để in ra giải thích "vì sao gán"); concept từ lookup không cần bằng chứng.
    """
    norm = normalize(q)
    normf = normalize(q, fold=True)
    found: set[str] = set()
    for text in (norm, normf):
        toks = text.split()
        for n in (4, 3, 2, 1):
            for i in range(len(toks) - n + 1):
                gram = " ".join(toks[i:i + n])
                if len(gram) < 3:
                    continue
                if gram in _syn:
                    found.update(_syn[gram])
    implicit = parse_implicit_intent(q)
    found.update(implicit)
    # NGỮ CẢNH "ngân sách": "budget/ngân sách" + một SỐ TIỀN ("budget 10 triệu") là khai báo
    # NGÂN SÁCH (-> range filter), KHÔNG phải phân khúc giá rẻ. Surface "budget" (en) khớp
    # PRICE_BUDGET ở bước lookup -> suppress khi đi kèm số tiền. Giữ "budget hotel" (không số) là
    # giá rẻ như cũ. parse_range lo phần range; ở đây chỉ gỡ concept hiểu sai.
    if "PRICE_BUDGET" in found and re.search(
        r"(budget|ngân sách|ngan sach)\D{0,6}[\d.,]+\s*(triệu|tr|trieu|k|nghìn|nghin|đồng|dong)",
        normalize(q, fold=True),
    ):
        found.discard("PRICE_BUDGET")
    return sorted(found), implicit


def parse_range(q: str) -> dict:
    """Bắt vài range filter phổ biến từ câu (giá triệu / điểm / sao)."""
    rf: dict = {}
    ql = q.lower()
    # tầm/khoảng X triệu -> dải quanh X (±30%)
    m = re.search(r"(tầm|khoảng|tầm khoảng|cỡ|xấp xỉ)\s*([\d.,]+)\s*(triệu|tr)", ql)
    if m:
        x = float(m.group(2).replace(",", ".")) * 1_000_000
        rf["price_min"] = int(x * 0.7)
        rf["price_max"] = int(x * 1.3)
    # dưới X triệu / tối đa
    m = re.search(r"(dưới|<|không quá|tối đa)\s*([\d.,]+)\s*(triệu|tr)", ql)
    if m:
        rf["price_max"] = int(float(m.group(2).replace(",", ".")) * 1_000_000)
        rf.pop("price_min", None)  # "dưới X" thì không có sàn
    # trên X điểm
    m = re.search(r"(trên|>|từ)\s*([\d.,]+)\s*điểm", ql)
    if m:
        rf["score_min"] = float(m.group(2).replace(",", "."))
    # N sao
    m = re.search(r"(\d)\s*sao", ql)
    if m:
        rf["star_eq"] = int(m.group(1))
    return rf


def parse_location_text(q: str) -> str | None:
    """Bắt địa danh thô (dùng để lọc theo text city/area — đơn giản, không qua LOC concept)."""
    # các thành phố hay gặp; mở rộng tùy ý
    cities = ["đà nẵng", "nha trang", "hà nội", "hồ chí minh", "sài gòn", "phú quốc",
              "đà lạt", "hội an", "huế", "hạ long", "vũng tàu", "sầm sơn", "quy nhơn",
              "phan thiết", "sa pa", "ninh bình", "cát bà", "côn đảo"]
    ql = normalize(q, fold=True)
    ql_nospace = ql.replace(" ", "")          # bắt cả dạng gõ liền: "danang", "nhatrang", "phuquoc"
    for c in cities:
        cf = normalize(c, fold=True)
        if cf in ql or cf.replace(" ", "") in ql_nospace:
            return c
    return None


# ---------------------------------------------------------------------------
# Lọc object
# ---------------------------------------------------------------------------
def _all_concepts(obj: dict) -> set[str]:
    sm = obj["semantic_metadata"]
    out: set[str] = set()
    for k, v in sm.items():
        if v is None:
            continue
        out.update(v if isinstance(v, list) else [v])
    return out


# Tập concept THỰC SỰ có mặt trên ít nhất 1 hotel trong corpus. Dùng để bỏ qua các hard
# concept "chết" khi lọc: vd SETTING_COASTAL/SETTING_CITY_CENTER/SETTING_ISLAND hiện 0 hotel
# (Bước 4 chưa suy ra setting) -> nếu một surface form ("ven biển") kéo theo concept rỗng đó
# rồi đưa vào AND lọc cứng thì LUÔN ra 0 kết quả GIẢ. Cùng tinh thần "giá fake -> không lọc
# cứng". Khi Bước 4 gắn được setting, concept tự "sống" lại, không cần sửa code.
_LIVE_CONCEPTS: set[str] = set()
for _o in _objs.values():
    _LIVE_CONCEPTS |= _all_concepts(_o)

FEEL_MIN = 0.6  # hotel phải đạt profile score >= ngưỡng cho concept cảm nhận mới tính "khớp"

# Tập concept CẢM NHẬN có ít nhất 1 hotel đạt ngưỡng FEEL_MIN. Nhiều STYLE_* (LUXURY,
# ROMANTIC, MODERN...) chưa hotel nào đạt -> nếu đưa vào lọc feel thì LUÔN 0 kết quả giả
# (giống _LIVE_CONCEPTS cho hard). Concept feel "chết" -> không lọc, chỉ để ranking
# (score() đã cộng feel_score nên hotel điểm thấp tự xuống cuối).
_LIVE_FEEL: set[str] = set()
for _o in _objs.values():
    for _c, _v in (_o.get("semantic_profile") or {}).items():
        if (_v or {}).get("score", 0) >= FEEL_MIN:
            _LIVE_FEEL.add(_c)


def search(q: str, limit: int = 15) -> dict:
    concepts, implicit = parse_concepts(q)
    rng = parse_range(q)
    loc = parse_location_text(q)
    # Phân loại concept giống tầng search thật:
    #   - HARD filter (AND bắt buộc): amenity + setting. Đây là "có/không" rõ ràng.
    #   - NỚI LỎNG (không lọc cứng): object_type ("khách sạn"=mọi lưu trú, xem golden Q1-01),
    #     purpose/style (cảm tính), price_tier (đã có range giá lo), location (lọc bằng TEXT
    #     vì object chưa gắn LOC concept — known limitation Bước 4).
    hard_all = [c for c in concepts if c.startswith(("AMEN_", "SETTING_"))]
    # Bỏ qua hard concept "chết" (0 hotel) khỏi AND -> tránh 0-kết-quả-giả (xem _LIVE_CONCEPTS).
    hard = [c for c in hard_all if c in _LIVE_CONCEPTS]
    hard_skipped = [c for c in hard_all if c not in _LIVE_CONCEPTS]
    soft = [c for c in concepts if c.startswith(("PURPOSE_", "OBJ_", "PRICE_"))]
    # CẢM NHẬN từ review (Bước 5 profile): style/aspect -> lọc theo semantic_profile score.
    feel_all = [c for c in concepts if c.startswith(("STYLE_", "ASPECT_"))]
    # Bỏ qua feel concept "chết" (0 hotel đạt ngưỡng) khỏi lọc -> tránh 0-kết-quả-giả; vẫn
    # góp vào ranking (xem _LIVE_FEEL). vd STYLE_LUXURY/STYLE_ROMANTIC chưa hotel nào đạt.
    feel = [c for c in feel_all if c in _LIVE_FEEL]
    feel_skipped = [c for c in feel_all if c not in _LIVE_FEEL]

    hits = []
    for obj in _objs.values():
        oc = _all_concepts(obj)
        prof = obj.get("semantic_profile", {})
        # AND mọi concept HARD (amenity/setting)
        if not all(c in oc for c in hard):
            continue
        # CẢM NHẬN: hotel phải có profile score đủ cao cho MỌI concept feel yêu cầu
        if not all((prof.get(c, {}).get("score", 0) >= FEEL_MIN) for c in feel):
            continue
        # object_type: nếu câu nói loại hình cụ thể (resort/villa...) thì lọc, trừ OBJ_HOTEL (hiểu rộng)
        want_obj = [c for c in soft if c.startswith("OBJ_") and c != "OBJ_HOTEL"]
        if want_obj and oc.isdisjoint(want_obj):
            continue
        # location text
        if loc:
            locblob = " ".join(
                str(obj["location"].get(k) or "") for k in ("city", "area", "province", "district")
            )
            if normalize(loc, fold=True) not in normalize(locblob, fold=True):
                continue
        rf = obj["range_filters"]
        # GIÁ: toàn bộ giá là placeholder (fake) -> KHÔNG loại cứng theo giá (tránh "0 kết quả"
        # giả). Chỉ dùng để SORT ưu tiên (xem score()). star/score thì lọc thật.
        if "score_min" in rng and (rf.get("review_score") or 0) < rng["score_min"]:
            continue
        if "star_eq" in rng and rf.get("star_rating") != rng["star_eq"]:
            continue
        hits.append(obj)

    # PURPOSE (vd PURPOSE_FAMILY) là SOFT -> KHÔNG lọc, chỉ ƯU TIÊN ranking: hotel có amenity
    # minh chứng cho mục đích đó (kids club/babysitting cho family...) được đẩy lên top.
    purposes = [c for c in concepts if c.startswith("PURPOSE_")]
    purpose_amen = set()
    for p in purposes:
        purpose_amen |= PURPOSE_EVIDENCE.get(p, set())

    # sort: ưu tiên hotel khớp nhiều concept SOFT + có amenity minh chứng PURPOSE; nếu câu có
    #       mức giá -> ưu tiên hotel giá GẦN mức đó (dù giá fake, vẫn là proxy); rồi review_score.
    target_price = rng.get("price_max") or rng.get("price_min")

    def score(o: dict):
        oc = _all_concepts(o)
        soft_hit = sum(1 for c in soft if c in oc)
        purpose_hit = len(purpose_amen & oc)  # số amenity khớp mục đích chuyến đi
        prof = o.get("semantic_profile", {})
        feel_score = sum(prof.get(c, {}).get("score", 0) for c in feel_all)  # tổng điểm cảm nhận (kể cả feel skip)
        rf = o["range_filters"]
        p = rf.get("price_min_vnd")
        if target_price and p and not rf.get("price_capped"):
            price_gap = abs(p - target_price)
        else:
            price_gap = 10**12
        return (-soft_hit, -purpose_hit, -feel_score, price_gap, -(rf.get("review_score") or 0))
    hits.sort(key=score)
    return {"concepts": concepts, "implicit": implicit, "hard": hard, "soft": soft, "feel": feel,
            "hard_skipped": hard_skipped, "feel_skipped": feel_skipped,
            "purpose_amen": sorted(purpose_amen),
            "range": rng, "location": loc, "n": len(hits), "hits": hits[:limit]}


# ---------------------------------------------------------------------------
# Intent "tìm ĐỊA ĐIỂM" (không phải tìm hotel) — trả lời từ nearby_places
# ---------------------------------------------------------------------------
PLACE_INTENT_KW = ["khu vui chơi", "vui chơi", "chơi gì", "tham quan", "địa điểm",
                   "điểm đến", "giải trí", "đi đâu", "có gì chơi", "thắng cảnh"]
# loại nearby (category) coi là "vui chơi/giải trí"
FUN_CATEGORIES = ["giải trí", "công viên", "vui chơi", "thể thao", "bãi biển",
                  "vườn", "thú", "cắm trại", "chợ"]


def is_place_intent(q: str) -> bool:
    ql = normalize(q, fold=True)
    return any(normalize(k, fold=True) in ql for k in PLACE_INTENT_KW)


def search_places(q: str, limit: int = 20) -> list[tuple]:
    """Gom nearby_places (loại vui chơi/giải trí) của hotel trong location -> địa điểm + tần suất."""
    loc = parse_location_text(q)
    from collections import Counter
    seen: dict[str, dict] = {}
    freq: Counter = Counter()
    for obj in _objs.values():
        if loc:
            blob = " ".join(str(obj["location"].get(k) or "") for k in ("city", "area", "province"))
            if normalize(loc, fold=True) not in normalize(blob, fold=True):
                continue
        for p in obj["nearby_places"]:
            nm, cat = p.get("name"), (p.get("category") or "")
            if not nm:
                continue
            if any(normalize(fc, fold=True) in normalize(cat, fold=True) for fc in FUN_CATEGORIES):
                freq[nm] += 1
                seen[nm] = {"name": nm, "category": cat}
    return [(seen[nm], n) for nm, n in freq.most_common(limit)]


def show(q: str) -> None:
    # nếu hỏi ĐỊA ĐIỂM -> trả địa điểm, không phải hotel
    if is_place_intent(q):
        loc = parse_location_text(q)
        places = search_places(q)
        print(f"\n❓ {q}")
        print(f"   → intent: TÌM ĐỊA ĐIỂM (không phải hotel) | location: {loc or '—'}")
        print(f"   → {len(places)} địa điểm vui chơi/giải trí (từ nearby_places của hotel quanh đó):")
        for pl, n in places:
            print(f"      • {pl['name'][:46]:46s} | {pl['category']}  (gần {n} hotel)")
        return

    r = search(q)
    print(f"\n❓ {q}")
    print(f"   → concept hiểu được: {r['concepts']}")
    if r["implicit"]:
        impl = ", ".join(f"{cid} (từ '{ev}')" for cid, ev in r["implicit"].items())
        print(f"   → intent NGẦM suy ra (từ mô tả hoàn cảnh): {impl}")
    if r["purpose_amen"]:
        print(f"   → ưu tiên hotel có tiện ích hợp mục đích: {r['purpose_amen']}")
    print(f"   → lọc CỨNG (amenity/setting): {r['hard'] or '—'} | nới lỏng: {r['soft'] or '—'}")
    if r["hard_skipped"]:
        print(f"   ⚠ bỏ qua hard concept 0 hotel (Bước 4 chưa gắn nhãn): {r['hard_skipped']}")
    if r["feel_skipped"]:
        print(f"   ⚠ bỏ qua feel concept 0 hotel đạt ngưỡng (Bước 5 chưa đủ profile): {r['feel_skipped']}")
    print(f"   → CẢM NHẬN (từ review, lọc theo profile≥0.6): {r['feel'] or '—'}")
    print(f"   → range: {r['range'] or '—'} | location: {r['location'] or '—'}")
    if "price_max" in r["range"] or "price_min" in r["range"]:
        print("   ⚠ GIÁ là placeholder (fake) — KHÔNG lọc cứng theo giá, chỉ ưu tiên hotel giá gần mức yêu cầu.")
    print(f"   → {r['n']} hotel khớp. Top (ưu tiên khớp nhiều tiêu chí + gần giá + điểm cao):")
    for o in r["hits"]:
        rf = o["range_filters"]
        cap = " [giá~cap5tr]" if rf.get("price_capped") else ""
        price = f"từ {rf.get('price_min_vnd', 0):,}đ/đêm" if rf.get("price_min_vnd") else "giá ?"
        score = f"{rf.get('review_score')}/10" if rf.get("review_score") else "—"
        star = f"{rf.get('star_rating')}★" if rf.get("star_rating") else "?★"
        # điểm cảm nhận của hotel cho các concept feel trong câu
        prof = o.get("semantic_profile", {})
        feel_str = " ".join(
            f"{c.split('_', 1)[1].lower()}={prof.get(c, {}).get('score', 0):.2f}" for c in r["feel"]
        )
        feel_str = f" | {feel_str}" if feel_str else ""
        # đánh dấu hotel có tiện ích hợp mục đích chuyến đi (lý do được ưu tiên lên top)
        matched = sorted(set(r["purpose_amen"]) & _all_concepts(o))
        purpose_str = f" | ✓hợp mục đích: {', '.join(c.split('_', 1)[1].lower() for c in matched)}" if matched else ""
        print(f"      • {o['title'][:42]:42s} | {o['location'].get('city')} "
              f"| {star} | review {score}{feel_str} | {price}{cap}{purpose_str}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        show(" ".join(sys.argv[1:]))
    else:
        # vài câu demo
        for q in [
            "khách sạn có hồ bơi ở Đà Nẵng",
            "resort gần biển cho gia đình ở Nha Trang",
            "resort hạng sang có spa ở Phú Quốc",
            "khách sạn cho cặp đôi có hồ bơi vô cực",
        ]:
            show(q)
