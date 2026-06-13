"""
extract_corpus.py
-----------------
Trích xuất toàn bộ hotel JSON trong data/ thành 1 file JSONL gọn để phục vụ
việc gán nhãn Golden dataset (ground truth top-k).

Mỗi dòng output = 1 khách sạn với các field cần cho việc chấm relevance:
  hotel_id, name, city, star_rating, accommodation_type, is_luxury,
  review_score, amenities (list), description (full text).

Cách chạy (từ thư mục d:\\Test):
    python evaluation/tools/extract_corpus.py

Output:
    evaluation/corpus/hotel_corpus.jsonl
"""

import json
import os
import glob

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "corpus")
OUT_FILE = os.path.join(OUT_DIR, "hotel_corpus.jsonl")

FIELDS = [
    "hotel_id",
    "name",
    "city",
    "area",
    "star_rating",
    "accommodation_type",
    "is_luxury",
    "review_score",
    "review_count",
]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    files = sorted(glob.glob(os.path.join(DATA_DIR, "hotel_*.json")))
    count = 0
    with open(OUT_FILE, "w", encoding="utf-8") as out:
        for fp in files:
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    h = json.load(f)
            except Exception as e:
                print(f"[SKIP] {os.path.basename(fp)}: {e}")
                continue

            rec = {k: h.get(k) for k in FIELDS}
            rec["amenities"] = h.get("amenities", [])
            rec["description"] = h.get("description", "")
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            count += 1

    size_mb = os.path.getsize(OUT_FILE) / (1024 * 1024)
    print(f"Done. {count} hotels -> {OUT_FILE} ({size_mb:.2f} MB)")


if __name__ == "__main__":
    main()
