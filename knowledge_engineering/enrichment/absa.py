"""absa.py — Aspect-Based Sentiment Analysis cho review (Sprint 2, Bước 5.3).

Owner: Trương Anh Long (KE, DA10). Mỗi review tiếng Việt -> trích cặp (khía cạnh, cảm xúc, span)
bằng LLM (qua llm.py đa-provider). Bổ sung cho SEED (5.2): thêm SPAN dẫn chứng + concept STYLE_*
ngoài 7 aspect mà aggregate Agoda không có.

NGUYÊN TẮC (mục 0.5 + 2.4):
  - concept TRUNG TÍNH: "hơi ồn" -> {STYLE_QUIET, negative}, KHÔNG tạo STYLE_NOT_QUIET.
  - aspect CHỈ trong 7 ASPECT_* (ràng buộc vocabulary). style chỉ trong tập cho phép.
  - mỗi review tối đa 1 phiếu/concept (dedupe ở aggregate 5.4).
  - LLM chỉ chạy review (ca khó/giàu thông tin); KHÔNG sửa ontology.

Chạy mẫu:
  .venv/Scripts/python.exe -X utf8 -m knowledge_engineering.enrichment.absa --hotel 805030 --limit 20
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

from knowledge_engineering.enrichment.llm import complete_json, active_config

REVIEWS_DIR = "data/raw/reviews"

# prompt_version: tăng khi SỬA prompt SYSTEM. Lưu vào evidence để biết evidence sinh từ bản nào
# (đổi prompt -> cache LLM vô hiệu, evidence cũ version cũ -> cần chạy lại). v1=vi-only, v2=đa ngôn ngữ.
PROMPT_VERSION = "v2-multilang"

# Vocabulary cho phép (ràng buộc LLM chỉ chọn trong đây)
ASPECTS = ["ASPECT_CLEANLINESS", "ASPECT_SERVICE", "ASPECT_LOCATION", "ASPECT_ROOM",
           "ASPECT_FOOD", "ASPECT_VALUE", "ASPECT_FACILITIES"]
STYLES = ["STYLE_QUIET", "STYLE_LIVELY", "STYLE_RELAXING", "STYLE_MODERN",
          "STYLE_ROMANTIC", "STYLE_LUXURY", "STYLE_ECO"]

SYSTEM = f"""Bạn trích cảm xúc theo khía cạnh (ABSA) từ review khách sạn.
Review CÓ THỂ bằng nhiều ngôn ngữ (Việt, Anh, Hàn, Nga, Trung...). Dù review ngôn ngữ nào,
vẫn trả về concept ID CHUNG (tiếng Anh) dưới đây và span trích NGUYÊN VĂN theo ngôn ngữ gốc.

aspect CHỈ chọn trong: {ASPECTS}
style (cảm nhận phong cách, tùy chọn) CHỈ chọn trong: {STYLES}

Quy tắc:
- Mỗi khía cạnh/phong cách được NHẮC tới -> 1 mục {{concept, sentiment, span}}.
- sentiment: positive | negative | neutral | mixed.
- span: trích NGUYÊN VĂN đoạn ngắn trong review làm bằng chứng.
- TRUNG TÍNH: "hơi ồn" -> {{"concept":"STYLE_QUIET","sentiment":"negative"}} (KHÔNG tạo NOT_QUIET).
- Không bịa khía cạnh review không nhắc tới. Không nhắc gì -> mảng rỗng.

CHỈ trả JSON đúng dạng:
{{"overall_sentiment":"positive|negative|neutral|mixed",
  "items":[{{"concept":"ASPECT_... hoặc STYLE_...","sentiment":"...","span":"..."}}]}}"""


def analyze_review(text: str) -> dict:
    """Trả {overall_sentiment, items:[{concept, sentiment, span}]}. Lọc concept ngoài vocab."""
    if not text or not text.strip():
        return {"overall_sentiment": "neutral", "items": []}
    out = complete_json(SYSTEM, text.strip()[:2000], temperature=0)
    allowed = set(ASPECTS) | set(STYLES)
    items = []
    seen = set()                       # DEDUPE: mỗi concept tối đa 1 phiếu/review (prompt yêu cầu
                                       # vậy nhưng LLM vẫn trả trùng) -> lọc tại nguồn, evidence sạch.
    for it in out.get("items", []) or []:
        if not isinstance(it, dict):
            continue
        c = it.get("concept")
        if c in allowed and c not in seen:
            seen.add(c)
            items.append({
                "concept": c,
                "sentiment": it.get("sentiment", "neutral"),
                "span": (it.get("span") or "")[:200],
            })
    return {"overall_sentiment": out.get("overall_sentiment", "neutral"), "items": items}


# evidence CHIA THEO HOTEL: review_evidence/hotel_<id>.json (mỗi hotel 1 file).
# Lý do (vs 1 file gộp): 112k review -> 1 file ~100MB ghi lại mỗi lần = chậm dần + hỏng
# cả mẻ. Theo hotel: resume/ghi nhanh (file nhỏ ~150KB), hỏng cục bộ, khớp pattern
# data/raw/reviews (1 file/hotel). profile gộp thì vẫn 1 file (hotel_profiles.json).
EVIDENCE_DIR = Path("knowledge_engineering/enrichment/review_evidence")


def _evidence_path(hotel_id: int) -> Path:
    return EVIDENCE_DIR / f"hotel_{hotel_id}.json"


def _load_evidence(hotel_id: int) -> dict:
    """Evidence đã có của 1 hotel (resume). Key = str(review_id) -> KHÔNG chạy lại."""
    p = _evidence_path(hotel_id)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_evidence(hotel_id: int, store: dict) -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    _evidence_path(hotel_id).write_text(
        json.dumps(store, ensure_ascii=False, indent=1), encoding="utf-8")


def _review_text(r: dict) -> str:
    text = r.get("text") or ""
    extra = " ".join(filter(None, [r.get("positives"), r.get("negatives")]))
    return (text + " " + extra).strip()


def _sample_balanced(reviews: list, limit: int | None) -> list:
    """Lấy mẫu CÂN BẰNG theo rating, KHÔNG phải `[:limit]`.

    Lý do: crawler dùng sort_strategy=low_first -> review ĐẦU file toàn điểm thấp
    (50 đầu rating ~5.7 vs 50 cuối ~9.5). Lấy `[:limit]` = chỉ đọc phần tệ nhất ->
    ABSA lệch tiêu cực. Giải: sắp theo rating rồi lấy CÁCH ĐỀU -> mẫu trải đủ tệ/TB/tốt.
    (Aspect score vẫn lấy từ SEED/Agoda — toàn bộ review, cân bằng sẵn. ABSA chỉ cần
    sự HIỆN DIỆN của style + span, nên mẫu cân bằng là đủ, không cần crawl lại.)
    """
    if not limit or limit >= len(reviews):
        return reviews
    ranked = sorted(reviews, key=lambda r: (r.get("rating") is None, r.get("rating") or 0))
    step = len(ranked) / limit
    return [ranked[int(i * step)] for i in range(limit)]


def analyze_hotel(hotel_id: int, limit: int | None = None, save_every: int = 10) -> dict:
    """Chạy ABSA cho review 1 hotel. LƯU INCREMENTAL + RESUME:
    - review_id đã có trong evidence store -> BỎ QUA (không gọi API lại).
    - cứ `save_every` review xong -> ghi file (lỗi giữa chừng không mất phần đã trả tiền).
    Trả dict {review_id: evidence}.
    """
    f = Path(REVIEWS_DIR) / f"hotel_{hotel_id}_reviews.json"
    if not f.exists():
        raise FileNotFoundError(f"Không có file review: {f}")
    reviews = json.loads(f.read_text(encoding="utf-8")).get("reviews", [])
    reviews = _sample_balanced(reviews, limit)   # cân bằng theo rating, KHÔNG [:limit]

    from datetime import datetime, timezone
    cfg = active_config()
    meta_run = {"provider": cfg["provider"], "model": cfg["model"],
                "prompt_version": PROMPT_VERSION}

    store = _load_evidence(hotel_id)
    done_before = len(store)
    processed = 0
    try:
        for r in reviews:
            rid = str(r.get("review_id"))
            if rid in store:           # đã chạy -> resume, không tốn tiền lại
                continue
            res = analyze_review(_review_text(r))
            store[rid] = {
                "review_id": r.get("review_id"),
                "hotel_id": hotel_id,
                "rating": r.get("rating"),
                "overall_sentiment": res["overall_sentiment"],
                "items": res["items"],
                # metadata: biết evidence sinh từ provider/model/prompt nào (đổi -> chạy lại)
                **meta_run,
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            processed += 1
            if processed % save_every == 0:
                _save_evidence(hotel_id, store)   # lưu định kỳ
    finally:
        _save_evidence(hotel_id, store)           # LUÔN lưu, kể cả khi raise giữa chừng
    print(f"  (đã có sẵn {done_before}, chạy mới {processed}, tổng {len(store)} evidence)")
    return store


# ---------------------------------------------------------------------------
# Ước lượng chi phí (gpt-4o-mini) — để xác nhận TRƯỚC khi đốt tiền
# ---------------------------------------------------------------------------
# giá 2025 (USD / 1M token)
PRICE = {"gpt-4o-mini": (0.15, 0.60), "gpt-4o": (2.50, 10.0)}


def list_review_hotels() -> list[int]:
    """Danh sách hotel_id có file review, sắp tăng dần (deterministic)."""
    import re
    ids = []
    for f in glob.glob(f"{REVIEWS_DIR}/hotel_*_reviews.json"):
        m = re.search(r"hotel_(\d+)_reviews", f)
        if m:
            ids.append(int(m.group(1)))
    return sorted(ids)


def estimate_cost(hotel_id: int, limit: int | None, model: str) -> dict:
    f = Path(REVIEWS_DIR) / f"hotel_{hotel_id}_reviews.json"
    reviews = json.loads(f.read_text(encoding="utf-8")).get("reviews", [])
    reviews = _sample_balanced(reviews, limit)   # cùng mẫu cân bằng như khi chạy thật
    store = _load_evidence(hotel_id)
    todo = [r for r in reviews if str(r.get("review_id")) not in store]
    avg_chars = sum(len(_review_text(r)) for r in todo) / max(1, len(todo))
    in_tok = 260 + avg_chars / 4          # system ~260 + review
    out_tok = 120
    pin, pout = PRICE.get(model, PRICE["gpt-4o-mini"])
    cost = len(todo) * (in_tok * pin + out_tok * pout) / 1_000_000
    return {"todo": len(todo), "skip_cached": len(reviews) - len(todo),
            "avg_chars": int(avg_chars), "est_usd": round(cost, 4)}


def _summarize(ev: dict) -> None:
    from collections import Counter
    cs = Counter(); n_items = 0
    for e in ev.values():
        for it in e["items"]:
            cs[(it["concept"], it["sentiment"])] += 1; n_items += 1
    print(f"  -> {len(ev)} review, {n_items} cặp (concept, sentiment).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="ABSA per-review. Chạy 1 hotel (--hotel) hoặc cả corpus (--all).")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--hotel", type=int, help="chạy 1 hotel")
    g.add_argument("--all", action="store_true", help="chạy nhiều hotel (batch)")
    ap.add_argument("--limit", type=int, default=20, help="số review/hotel (mẫu cân bằng)")
    ap.add_argument("--max-hotels", type=int, default=None, help="[batch] tối đa N hotel")
    ap.add_argument("--budget-usd", type=float, default=None,
                    help="[batch] DỪNG khi tổng dự toán vượt ngân sách này (chặn cứng chi phí)")
    ap.add_argument("--dry-run", action="store_true", help="CHỈ dự toán, KHÔNG gọi API")
    ap.add_argument("--yes", action="store_true", help="bỏ xác nhận (chạy thẳng)")
    args = ap.parse_args()

    cfg = active_config()
    is_openai = cfg["provider"] == "openai"
    print(f"LLM: {cfg['provider']}/{cfg['model']}\n")

    # ----- danh sách hotel cần chạy -----
    if args.all:
        hotels = list_review_hotels()
        if args.max_hotels:
            hotels = hotels[:args.max_hotels]
    else:
        hotels = [args.hotel]

    # ----- DỰ TOÁN toàn bộ TRƯỚC (gom + chặn ngân sách) -----
    plan = []           # (hotel_id, est) — chỉ hotel còn review todo, trong ngân sách
    total_cost = 0.0; total_todo = 0; skipped_budget = 0
    for hid in hotels:
        try:
            est = estimate_cost(hid, args.limit, cfg["model"])
        except FileNotFoundError:
            continue
        if est["todo"] == 0:
            continue
        # chặn ngân sách: nếu cộng hotel này vượt budget -> dừng nhận thêm
        if args.budget_usd is not None and is_openai and total_cost + est["est_usd"] > args.budget_usd:
            skipped_budget = len([h for h in hotels if h >= hid])  # ước lượng còn lại
            break
        plan.append((hid, est)); total_cost += est["est_usd"]; total_todo += est["todo"]

    print(f"=== DỰ TOÁN {'(BATCH)' if args.all else ''} ===")
    print(f"  hotel sẽ chạy   : {len(plan)}" + (f" (cắt vì ngân sách, bỏ ~{skipped_budget})" if skipped_budget else ""))
    print(f"  review chạy mới : {total_todo}")
    if is_openai:
        print(f"  CHI PHÍ ƯỚC TÍNH: ${round(total_cost,4)}  (model {cfg['model']}"
              + (f", trần ${args.budget_usd}" if args.budget_usd else "") + ")")
    else:
        print(f"  provider {cfg['provider']} — miễn phí/local")

    if not plan:
        print("\nKhông có review mới để chạy. Dừng."); sys.exit(0)
    if args.dry_run:
        print("\n--dry-run: CHỈ dự toán, không gọi API."); sys.exit(0)

    if is_openai and not args.yes:
        ans = input(f"\n>>> Chạy {total_todo} review / {len(plan)} hotel (~${round(total_cost,4)})? gõ 'yes': ")
        if ans.strip().lower() != "yes":
            print("Đã hủy — không gọi API, không tốn tiền."); sys.exit(0)

    # ----- CHẠY -----
    print()
    for i, (hid, est) in enumerate(plan, 1):
        print(f"[{i}/{len(plan)}] hotel {hid} (~{est['todo']} review)...")
        ev = analyze_hotel(hid, args.limit)
        _summarize(ev)
    print(f"\nXong {len(plan)} hotel. Evidence -> {EVIDENCE_DIR}/hotel_*.json")
