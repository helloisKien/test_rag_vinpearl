"""
find_candidates.py
------------------
Quét hotel_corpus.jsonl theo từng "chủ đề" (mỗi chủ đề = nhóm từ khóa)
và xuất báo cáo ứng viên cho việc gán nhãn Golden dataset.

Chỉ tìm trong phần `description` (KHÔNG tìm trong amenities) -> đảm bảo thông tin
trả lời chỉ đến từ hotel description.

Cách chạy (từ d:\\Test):
    python evaluation/tools/find_candidates.py

Output:
    evaluation/tools/candidates_report.txt
"""

import json
import os
import re
import unicodedata

CORPUS = os.path.join(os.path.dirname(__file__), "..", "corpus", "hotel_corpus.jsonl")
OUT = os.path.join(os.path.dirname(__file__), "candidates_report.txt")


def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D").lower()


# Mỗi chủ đề: tên + danh sách "must-have" keyword groups.
# Một KS là ứng viên nếu khớp >= 1 keyword (đếm số keyword khác nhau để xếp hạng thô).
THEMES = {
    "T1_kien_truc_phap_co_dien": [
        "kien truc phap", "kien truc thuoc dia", "kien truc dong duong",
        "co dien", "phong cach phap", "thoi phap", "tan co dien",
    ],
    "T2_resort_tren_dao_biet_lap": [
        "tren dao", "hon dao", "oc dao", "biet lap", "tach biet",
        "dao rieng", "hoang so",
    ],
    "T3_pho_co": [
        "pho co", "khu pho co", "trung tam pho co", "phong cach hoi an",
    ],
    "T4_ven_song": [
        "ven song", "ben song", "bo song", "canh song", "dong song",
        "song han", "song huong", "song sai gon",
    ],
    "T5_binh_minh_hoang_hon": [
        "binh minh", "hoang hon", "mat troi moc", "mat troi lan",
        "ngam binh minh", "ngam hoang hon",
    ],
    "T6_moi_khai_truong": [
        "moi khai truong", "vua khai truong", "moi di vao hoat dong",
        "moi xay dung", "xay dung vao nam 2022", "xay dung vao nam 2023",
        "xay dung vao nam 2024", "khanh thanh", "vua moi mo cua",
    ],
    "T7_tren_doi_nui": [
        "tren doi", "lung chung nui", "tren nui", "trien nui", "ngon doi",
        "nhin xuong thung lung", "cao nguyen", "doi nui",
    ],
    "T8_gan_cho_dem": [
        "cho dem", "gan cho dem",
    ],
    "T9_boutique": [
        "boutique", "am cung", "nho xinh", "phong cach boutique",
    ],
    "T10_vuon_nhiet_doi": [
        "vuon nhiet doi", "khu vuon xanh", "vuon cay xanh", "cay xanh mat",
        "khong gian xanh", "vuon rong",
    ],
    "T11_gan_san_bay": [
        "gan san bay", "sat san bay", "ngay canh san bay",
        "cach san bay 5 phut", "cach san bay 10 phut", "cach san bay 15 phut",
    ],
    "T12_spa_nghi_duong_thu_gian": [
        "yen tinh", "tinh lang", "thu gian", "thanh binh", "tron khoi pho thi",
    ],
}


def snippet(desc_lc_orig, desc_norm, kw, width=110):
    idx = desc_norm.find(kw)
    if idx < 0:
        return ""
    start = max(0, idx - width)
    end = min(len(desc_lc_orig), idx + len(kw) + width)
    s = desc_lc_orig[start:end].replace("\n", " ")
    return ("..." if start > 0 else "") + s + ("..." if end < len(desc_lc_orig) else "")


def main():
    hotels = []
    with open(CORPUS, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            h = json.loads(line)
            h["_desc_norm"] = strip_accents(h.get("description", ""))
            hotels.append(h)

    lines = []
    for theme, kws in THEMES.items():
        cands = []
        for h in hotels:
            dn = h["_desc_norm"]
            hit_kws = [kw for kw in kws if kw in dn]
            if not hit_kws:
                continue
            cands.append((len(hit_kws), h.get("review_score") or 0, h, hit_kws))
        # sap xep: nhieu keyword -> review_score cao
        cands.sort(key=lambda x: (x[0], x[1]), reverse=True)

        lines.append("=" * 90)
        lines.append(f"THEME {theme}  (matched hotels: {len(cands)})")
        lines.append("=" * 90)
        for n_hit, rs, h, hit_kws in cands[:14]:
            desc = h.get("description", "")
            snip = snippet(desc, h["_desc_norm"], hit_kws[0])
            lines.append(
                f"[{h.get('hotel_id')}] {h.get('name')} | {h.get('city')} | "
                f"{h.get('star_rating')}* | {h.get('accommodation_type')} | "
                f"review={rs} | hits={n_hit}:{hit_kws}"
            )
            lines.append(f"    > {snip}")
        lines.append("")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Done. Report -> {OUT}  ({len(hotels)} hotels scanned)")


if __name__ == "__main__":
    main()
