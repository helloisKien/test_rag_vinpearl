"""
extract_policies.py
--------------------
Trích xuất phần policies (secondary.hotel_policy.policyNotes + childPolicies +
extrabedPolicies + other_policies) và amenities của toàn bộ hotel JSON.

Cách chạy (từ d:\\Test):
    python evaluation/tools/extract_policies.py

Output:
    evaluation/corpus/policies_corpus.jsonl   (mỗi dòng = 1 KS: policy_text + amenities)
    evaluation/tools/policies_amenities_stats.txt
"""

import json
import os
import glob
import re
import unicodedata
from collections import Counter

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "corpus")
OUT_CORPUS = os.path.join(OUT_DIR, "policies_corpus.jsonl")
OUT_STATS = os.path.join(os.path.dirname(__file__), "policies_amenities_stats.txt")


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D").lower()


# Các nhóm từ khóa policy để đếm tần suất (đoán chủ đề có đủ dữ liệu)
POLICY_KW = {
    "thu_cung_pet": ["thu cung", "vat nuoi", "thu nuoi"],
    "hut_thuoc": ["hut thuoc", "khong hut thuoc"],
    "huy_hoan": ["huy phong", "chinh sach huy", "hoan tien", "khong hoan"],
    "dat_coc": ["dat coc", "tien coc", "tien dat coc", "the chap"],
    "giay_to": ["giay to tuy than", "chung minh", "can cuoc", "ho chieu", "giay khai sinh"],
    "tre_em_mien_phi": ["mien phi", "0-3 tuoi", "0 - 3 tuoi", "tre em"],
    "le_gala": ["gala", "giang sinh", "nam moi", "tet"],
    "giuong_phu": ["giuong phu"],
    "do_tuoi_nhan_phong": ["do tuoi", "tuoi toi thieu", "18 tuoi", "tu 18"],
    "thanh_toan": ["tien mat", "thanh toan", "the tin dung"],
}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    files = sorted(glob.glob(os.path.join(DATA_DIR, "hotel_*.json")))

    policy_kw_counter = Counter()
    amenity_counter = Counter()
    n_policy = 0
    count = 0

    with open(OUT_CORPUS, "w", encoding="utf-8") as out:
        for fp in files:
            try:
                h = json.load(open(fp, encoding="utf-8"))
            except Exception as e:
                print(f"[SKIP] {os.path.basename(fp)}: {e}")
                continue

            sec = h.get("secondary") or {}
            hp = sec.get("hotel_policy") or {}
            notes = list(hp.get("policyNotes") or [])
            for cp in hp.get("childPolicies") or []:
                if isinstance(cp, dict):
                    notes.append(cp.get("description", ""))
            for ep in hp.get("extrabedPolicies") or []:
                if isinstance(ep, dict):
                    notes.append(ep.get("description", ""))
            for op in sec.get("other_policies") or []:
                if isinstance(op, str):
                    notes.append(op)
                elif isinstance(op, dict):
                    notes.append(json.dumps(op, ensure_ascii=False))

            policy_text = "\n".join(n for n in notes if n)
            amenities = h.get("amenities") or []

            if policy_text.strip():
                n_policy += 1
                pn = norm(policy_text)
                for label, kws in POLICY_KW.items():
                    if any(k in pn for k in kws):
                        policy_kw_counter[label] += 1

            for a in amenities:
                amenity_counter[a] += 1

            rec = {
                "hotel_id": h.get("hotel_id"),
                "name": h.get("name"),
                "city": h.get("city"),
                "accommodation_type": h.get("accommodation_type"),
                "review_score": h.get("review_score"),
                "policy_notes": notes,
                "amenities": amenities,
            }
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            count += 1

    lines = [f"Total hotels: {count} | có policy_notes: {n_policy}", ""]
    lines.append("=== POLICY KEYWORD COUNTS (số KS có policy khớp) ===")
    for label, c in policy_kw_counter.most_common():
        lines.append(f"{c:5d}  {label}")
    lines.append("")
    lines.append("=== AMENITY TAG COUNTS (top 100) ===")
    for a, c in amenity_counter.most_common(100):
        lines.append(f"{c:5d}  {a}")

    with open(OUT_STATS, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Done. Corpus -> {OUT_CORPUS}")
    print(f"Stats  -> {OUT_STATS}")


if __name__ == "__main__":
    main()
