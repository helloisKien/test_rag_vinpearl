"""
extract_faq_activities.py
-------------------------
Trích xuất phần `faq` và `activities` của toàn bộ hotel JSON trong data/
thành 1 corpus gọn (JSONL) + 1 file thống kê để thiết kế Golden dataset.

Cách chạy (từ d:\\Test):
    python evaluation/tools/extract_faq_activities.py

Output:
    evaluation/corpus/faq_activities_corpus.jsonl   (mỗi dòng = 1 KS)
    evaluation/tools/faq_activities_stats.txt        (thống kê category + keyword)
"""

import json
import os
import glob
import re
from collections import Counter

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "corpus")
OUT_CORPUS = os.path.join(OUT_DIR, "faq_activities_corpus.jsonl")
OUT_STATS = os.path.join(os.path.dirname(__file__), "faq_activities_stats.txt")


def get_price(act):
    try:
        t = act["price"]["display"]["perBook"]["total"]["allInclusive"]["chargeTotal"]
        return int(t)
    except Exception:
        return None


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    files = sorted(glob.glob(os.path.join(DATA_DIR, "hotel_*.json")))

    cat_counter = Counter()
    act_word_counter = Counter()
    n_with_faq = 0
    n_with_act = 0
    count = 0

    with open(OUT_CORPUS, "w", encoding="utf-8") as out:
        for fp in files:
            try:
                h = json.load(open(fp, encoding="utf-8"))
            except Exception as e:
                print(f"[SKIP] {os.path.basename(fp)}: {e}")
                continue

            faq = h.get("faq") or []
            acts = h.get("activities") or []

            faq_slim = [
                {"q": x.get("question") or "", "a": x.get("answer") or "",
                 "cat": x.get("category") or ""}
                for x in faq
            ]
            act_slim = [
                {"title": x.get("title") or "", "desc": x.get("description") or "",
                 "score": x.get("review_score") or 0, "price": get_price(x)}
                for x in acts
            ]

            if faq_slim:
                n_with_faq += 1
            if act_slim:
                n_with_act += 1

            for x in faq_slim:
                cat_counter[x["cat"]] += 1
            for x in act_slim:
                for w in re.findall(r"[A-Za-zÀ-ỹ]+", (x["title"] or "").lower()):
                    if len(w) >= 4:
                        act_word_counter[w] += 1

            rec = {
                "hotel_id": h.get("hotel_id"),
                "name": h.get("name"),
                "city": h.get("city"),
                "accommodation_type": h.get("accommodation_type"),
                "review_score": h.get("review_score"),
                "faq": faq_slim,
                "activities": act_slim,
            }
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            count += 1

    lines = []
    lines.append(f"Total hotels: {count} | có faq: {n_with_faq} | có activities: {n_with_act}")
    lines.append("")
    lines.append("=== FAQ CATEGORIES (count) ===")
    for cat, c in cat_counter.most_common():
        lines.append(f"{c:5d}  {cat}")
    lines.append("")
    lines.append("=== ACTIVITY TITLE KEYWORDS (top 120) ===")
    for w, c in act_word_counter.most_common(120):
        lines.append(f"{c:5d}  {w}")

    with open(OUT_STATS, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Done. Corpus -> {OUT_CORPUS}")
    print(f"Stats  -> {OUT_STATS}")


if __name__ == "__main__":
    main()
