"""profile_builder.py — Hotel Semantic Profile (Sprint 2, Bước 5.2 SEED + 5.4 aggregate).

Owner: Trương Anh Long (KE, DA10). Xây hotel_semantic_profile: điểm RIÊNG của từng hotel
trên concept (BA THỨ TÁCH BIỆT — Phần 0.5). KHÔNG sửa ontology.

Bước 5.2 (SEED, KHÔNG LLM): từ aggregate Agoda có sẵn:
  - rating_breakdown (7 aspect, điểm /10)        -> ASPECT_* score = điểm/10, nguồn=agoda_grades.
  - reviews_detail.tags (tag, mentioned, pos_pct) -> concept; pos/neg suy từ pos_pct*mentioned,
                                                     score = Wilson lower bound (ít data -> thấp hơn).
Bước 5.3 (ABSA per-review, LLM) sẽ THÊM evidence vào cùng cấu trúc -> aggregate lại (5.4).

Lớp dữ liệu (tách, mục 2.4d): profile = {hotel_id: {concept: {score,pos,neg,evidence_count,source,nature}}}.

Chạy: .venv/Scripts/python.exe -X utf8 -m knowledge_engineering.enrichment.profile_builder
"""

from __future__ import annotations

import glob
import json
import math
from collections import defaultdict

import yaml

HOTELS_GLOB = "data/cleaned/hotel_*.json"
MAP_YAML = "ontology/review_tag_map.yaml"
OUT_JSON = "knowledge_engineering/enrichment/hotel_profiles.json"
EVIDENCE_DIR = "knowledge_engineering/enrichment/review_evidence"

_map = yaml.safe_load(open(MAP_YAML, encoding="utf-8"))
RB_MAP = _map["rating_breakdown"]
TAG_MAP = _map["review_tags"]

# Phân vai 2 nguồn (sau khi đo: review crawl thiên-thấp -> ABSA mẫu lệch tiêu cực):
#   - ASPECT score  : LẤY TỪ SEED (rating_breakdown = toàn bộ review Agoda, cân bằng).
#                     KHÔNG đè bằng ABSA (mẫu crawl không đại diện tỷ lệ pos/neg).
#   - STYLE + span  : LẤY TỪ ABSA (seed/Agoda không có tag style). Chỉ cần sự HIỆN DIỆN,
#                     không cần tỷ lệ cân bằng -> mẫu crawl dùng được.
ABSA_MIN_EVIDENCE = 3   # cần >=3 review nhắc style mới đưa vào profile (tránh 1 review lẻ)


def wilson_lower_bound(pos: int, n: int, z: float = 1.96) -> float:
    """Wilson lower bound — ít evidence -> score thấp hơn raw (không overconfident)."""
    if n == 0:
        return 0.0
    phat = pos / n
    denom = 1 + z * z / n
    centre = phat + z * z / (2 * n)
    margin = z * math.sqrt((phat * (1 - phat) + z * z / (4 * n)) / n)
    return max(0.0, (centre - margin) / denom)


def seed_from_hotel(hotel: dict) -> dict[str, dict]:
    """Seed profile 1 hotel từ aggregate Agoda. concept -> {score,pos,neg,evidence_count,source,nature}."""
    prof: dict[str, dict] = {}
    rd = hotel.get("reviews_detail") or {}

    # (1) rating_breakdown -> ASPECT score = điểm/10 (tổng hợp TOÀN BỘ review).
    #     score_source ghi rõ nguồn của SCORE (tách khỏi mention bên dưới).
    n_reviews = rd.get("review_count") or hotel.get("review_count") or 0
    for name, score10 in (hotel.get("rating_breakdown") or {}).items():
        cid = RB_MAP.get(name)
        if cid and isinstance(score10, (int, float)):
            prof[cid] = {
                "score": round(score10 / 10.0, 3),
                "score_source": "agoda_grades(all reviews)",
                "evidence_count": n_reviews,
                "source": "agoda_grades",
                "nature": "experience",
            }

    # (2) reviews_detail.tags -> mention pos/neg. LƯU Ý 2 NGUỒN KHÁC NHAU:
    #     score (trên) = grades toàn bộ; mention_pos/neg (dưới) = SỐ REVIEW NHẮC TỚI aspect
    #     (Agoda chỉ trích vài trăm review tiêu biểu, KHÔNG phải toàn bộ). 2 số đo việc khác
    #     nhau -> KHÔNG đá nhau, đánh dấu rõ mention_source để người đọc không hiểu nhầm.
    for t in rd.get("tags", []) or []:
        if not isinstance(t, dict):
            continue
        cid = TAG_MAP.get(t.get("tag"))
        if not cid:
            continue
        mentioned = int(t.get("mentioned") or 0)
        pos = round(mentioned * float(t.get("positive_pct") or 0) / 100.0)
        neg = mentioned - pos
        if cid in prof and prof[cid].get("source") == "agoda_grades":
            # aspect đã có score từ grades -> CHỈ thêm mention (đánh dấu nguồn riêng), KHÔNG đè score.
            prof[cid]["mention_pos"] = pos
            prof[cid]["mention_neg"] = neg
            prof[cid]["mention_source"] = "agoda_tags(mentioned)"
        else:
            nat = "presence" if cid.startswith(("AMEN_", "PURPOSE_")) else "experience"
            prof[cid] = {
                "score": round(wilson_lower_bound(pos, mentioned), 3),
                "score_source": "agoda_tags(mentioned)",
                "pos": pos, "neg": neg,
                "evidence_count": mentioned,
                "source": "agoda_review_tags", "nature": nat,
            }
    return prof


def merge_absa(hotel_id: int, prof: dict[str, dict]) -> None:
    """Bổ sung từ ABSA evidence (nếu có file). 2 vai theo điểm mạnh nguồn:

      - ASPECT_* : score GIỮ TỪ SEED (Agoda toàn bộ review, cân bằng). ABSA chỉ THÊM
                   SPAN dẫn chứng tích cực (để DA09 giải thích "vì sao sạch").
      - STYLE_*  : nếu seed CHƯA có -> ABSA đóng góp cả score (Wilson) + span. Nếu seed
                   đã có -> chỉ thêm span (mẫu crawl thiên-thấp không đủ tin đè score).
    Span lấy review TÍCH CỰC (vì aspect score = % khen -> dẫn chứng nên là khen).
    """
    import os
    p = os.path.join(EVIDENCE_DIR, f"hotel_{hotel_id}.json")
    if not os.path.exists(p):
        return
    ev = json.load(open(p, encoding="utf-8"))
    pos: dict[str, int] = {}
    neg: dict[str, int] = {}
    span: dict[str, str] = {}     # span TÍCH CỰC (ưu tiên) làm dẫn chứng
    for e in ev.values():
        seen = set()
        for it in e.get("items", []):
            c = it.get("concept", "")
            if not c.startswith(("ASPECT_", "STYLE_")) or c in seen:
                continue
            seen.add(c)
            if it.get("sentiment") == "positive":
                pos[c] = pos.get(c, 0) + 1
                span.setdefault(c, it.get("span", ""))
            elif it.get("sentiment") == "negative":
                neg[c] = neg.get(c, 0) + 1

    for c in set(pos) | set(neg) | set(span):
        # ASPECT: chỉ thêm span (nếu seed có concept đó), KHÔNG đụng score.
        if c.startswith("ASPECT_"):
            if c in prof and span.get(c):
                prof[c]["span"] = span[c]
            continue
        # STYLE: là cặp ĐỐI NGHĨA (sôi động↔yên tĩnh), KHÔNG phải thang tốt↔xấu như aspect.
        # "chê ồn" (neg cho LIVELY) KHÔNG có nghĩa "hotel kém sôi động" -> nếu tính cả neg thì
        # ra STYLE_LIVELY=0.02 vô nghĩa. GIẢI: score style = sự HIỆN DIỆN TÍCH CỰC ('hotel này
        # CÓ phong cách X'); chỉ đếm positive, bỏ negative. Concept toàn negative -> LOẠI.
        p = pos.get(c, 0)
        if p < ABSA_MIN_EVIDENCE:        # cần >=3 phiếu KHEN mới công nhận phong cách này
            continue
        if c in prof and prof[c].get("source") in ("agoda_review_tags", "agoda_grades"):
            prof[c]["span"] = span.get(c, "")   # seed giữ score, ABSA thêm span
            continue
        # score = tỷ lệ KHEN trên tổng nhắc; nhưng tối thiểu dựa positive (presence).
        n = p + neg.get(c, 0)
        prof[c] = {
            "score": round(wilson_lower_bound(p, n), 3),
            "pos": p, "neg": neg.get(c, 0),
            "evidence_count": n,
            "span": span.get(c, ""),
            "source": "absa", "nature": "experience",
        }


def run() -> dict:
    profiles: dict[str, dict] = {}
    stats = {"n": 0, "with_profile": 0, "concept_hits": defaultdict(int), "no_data": 0}
    for f in sorted(glob.glob(HOTELS_GLOB)):
        hotel = json.load(open(f, encoding="utf-8"))
        hid = hotel.get("hotel_id")
        key = f"acc_{hid}"
        prof = seed_from_hotel(hotel)
        merge_absa(hid, prof)              # ASPECT: thêm span; STYLE: score+span từ ABSA
        profiles[key] = prof
        stats["n"] += 1
        if prof:
            stats["with_profile"] += 1
        else:
            stats["no_data"] += 1
        for c in prof:
            stats["concept_hits"][c] += 1
    json.dump(profiles, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return stats


if __name__ == "__main__":
    s = run()
    print(f"Hotels: {s['n']} | có profile seed: {s['with_profile']} | không data: {s['no_data']}")
    print("Concept phủ (số hotel):")
    for c, n in sorted(s["concept_hits"].items(), key=lambda x: -x[1]):
        print(f"  {n:4d}  {c}")
    print(f"-> {OUT_JSON}")
