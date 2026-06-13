"""
map_names_to_ids.py
-------------------
Đổi các phần tử trong relevant_hotel_ids của golden_set_v1.json từ TÊN khách sạn
sang hotel_id (số), dựa trên bảng ánh xạ name -> hotel_id trong hotel_corpus.jsonl.

An toàn: chỉ ghi đè file khi TẤT CẢ tên đều khớp. Nếu có tên không khớp,
script KHÔNG sửa file mà chỉ in danh sách tên chưa khớp để xử lý trước.

Cách chạy (từ d:\\Test):
    python evaluation/tools/map_names_to_ids.py

Output (khi mọi tên khớp):
    ghi đè golden_dataset/golden_set_v1.json (relevant_hotel_ids -> list số hotel_id)
"""

import json
import os
import unicodedata

HERE = os.path.dirname(__file__)
CORPUS = os.path.join(HERE, "..", "corpus", "hotel_corpus.jsonl")
GOLDEN = os.path.join(HERE, "..", "..", "golden_dataset", "golden_set_v1.json")


def norm(s):
    s = unicodedata.normalize("NFC", (s or "").strip())
    # gộp nhiều khoảng trắng thành 1
    return " ".join(s.split())


def main():
    # 1) build map name -> id (exact NFC-normalized)
    name2id = {}
    with open(CORPUS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            h = json.loads(line)
            name2id[norm(h.get("name"))] = h.get("hotel_id")

    # 2) load golden
    with open(GOLDEN, encoding="utf-8") as f:
        data = json.load(f)

    unmatched = []
    total = 0
    for q in data.get("queries", []):
        for name in q.get("relevant_hotel_ids", []):
            total += 1
            if isinstance(name, int):
                continue  # đã là id
            if norm(name) not in name2id:
                unmatched.append((q.get("query_id"), name))

    print(f"Tong so phan tu relevant_hotel_ids: {total}")
    print(f"So ten KHONG khop: {len(unmatched)}")
    if unmatched:
        print("--- DANH SACH TEN CHUA KHOP (query_id | name) ---")
        for qid, name in unmatched:
            print(f"  {qid} | {name}")
        print("\n=> KHONG ghi de file. Vui long sua cac ten tren cho khop voi hotel_corpus.jsonl roi chay lai.")
        return

    # 3) tất cả khớp -> thay thế
    for q in data.get("queries", []):
        ids = []
        for name in q.get("relevant_hotel_ids", []):
            ids.append(name if isinstance(name, int) else name2id[norm(name)])
        q["relevant_hotel_ids"] = ids

    # cập nhật ghi chú để phản ánh đã là id
    meta = data.get("metadata", {})
    if "ground_truth_note" in meta:
        meta["ground_truth_note"] = meta["ground_truth_note"].replace(
            "relevant_hotel_ids tạm thời chứa DANH SÁCH TÊN khách sạn (chưa map sang hotels.id)",
            "relevant_hotel_ids chứa DANH SÁCH hotel_id (đã map từ tên qua hotel_corpus.jsonl)",
        )

    with open(GOLDEN, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"OK: da ghi de {GOLDEN} voi relevant_hotel_ids = list hotel_id.")


if __name__ == "__main__":
    main()
