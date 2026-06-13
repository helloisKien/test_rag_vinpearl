"""
find_pol_amen_candidates.py
---------------------------
Tìm ứng viên Golden query cho 2 nhóm:
  - POLICY  : câu trả lời nằm trong secondary policyNotes
  - AMENITY : câu trả lời nằm trong trường amenities

In ma trận (theme x city, count>=5) + chi tiết top 8/ city cho 3 city nhiều nhất.

Cách chạy (từ d:\\Test):
    python evaluation/tools/find_pol_amen_candidates.py

Output:
    evaluation/tools/pol_amen_candidates.txt
"""

import json
import os
import unicodedata
from collections import defaultdict

CORPUS = os.path.join(os.path.dirname(__file__), "..", "corpus", "policies_corpus.jsonl")
OUT = os.path.join(os.path.dirname(__file__), "pol_amen_candidates.txt")


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D").lower()


# POLICY themes: (label, keywords[]) - tìm trong policy_notes (đã normalize)
POLICY_THEMES = [
    ("pol_child_free",   ["0-3 tuoi", "0 - 3 tuoi", "tre em duoi", "o mien phi", "mien phi neu o cung", "tre em tu 0"]),
    ("pol_extra_bed",    ["giuong phu"]),
    ("pol_id_required",  ["giay to tuy than", "chung minh nhan dan", "can cuoc", "ho chieu"]),
    ("pol_deposit",      ["dat coc", "tien coc", "the chap"]),
    ("pol_holiday_gala", ["gala", "giang sinh", "nam moi"]),
    ("pol_smoking",      ["hut thuoc"]),
    ("pol_min_age",      ["do tuoi nhan phong", "tuoi toi thieu", "tu 18 tuoi", "18 tuoi tro len"]),
    ("pol_pet",          ["thu cung", "vat nuoi"]),
    ("pol_payment_cash", ["tien mat", "the tin dung", "thanh toan"]),
    ("pol_checkin_doc",  ["chinh sach", "quy dinh"]),
]

# AMENITY themes: (label, tag_substrings_norm[]) - tìm trong từng phần tử amenities
AMENITY_THEMES = [
    ("amen_outdoor_pool", ["be boi ngoai troi"]),
    ("amen_pool_bar",     ["quan bar canh be boi", "bar canh be boi"]),
    ("amen_kids_pool",    ["be boi tre em"]),
    ("amen_gym",          ["phong tap"]),
    ("amen_spa_massage",  ["mat-xa", "mat xa", "spa xong"]),
    ("amen_garden",       ["vuon"]),
    ("amen_meeting",      ["phong hop", "co so vat chat cho hop"]),
    ("amen_playground",   ["san choi"]),
    ("amen_nonsmoking",   ["khong hut thuoc", "phong khong hut thuoc"]),
    ("amen_airport_shuttle", ["dua don san bay"]),
    ("amen_restaurant",   ["nha hang"]),
    ("amen_private_beach",["bai bien rieng"]),
]


def policy_match(h, kws):
    blob = norm("\n".join(h.get("policy_notes") or []))
    for kw in kws:
        if kw in blob:
            # tìm note gốc chứa kw để in snippet
            for note in h.get("policy_notes") or []:
                if kw in norm(note):
                    return note
            return "(matched)"
    return None


def amenity_match(h, subs):
    for a in h.get("amenities") or []:
        na = norm(a)
        if any(s in na for s in subs):
            return a
    return None


def section(hotels, themes, matcher, title):
    lines = [f"##################### {title}: MATRIX (theme x city, count>=5) #####################"]
    detail = []
    for label, kws in themes:
        by_city = defaultdict(list)
        for h in hotels:
            m = matcher(h, kws)
            if m is not None:
                by_city[h.get("city") or "?"].append((h.get("review_score") or 0, h, m))
        good = {c: v for c, v in by_city.items() if len(v) >= 5}
        lines.append(f"\n### {label} (kws={kws})")
        for c, v in sorted(good.items(), key=lambda x: -len(x[1]))[:8]:
            lines.append(f"    {len(v):3d}  {c}")
        for c, v in sorted(good.items(), key=lambda x: -len(x[1]))[:3]:
            v.sort(key=lambda x: x[0], reverse=True)
            detail.append("=" * 90)
            detail.append(f"{label} | city={c} | n={len(v)}")
            detail.append("=" * 90)
            for rs, h, m in v[:8]:
                detail.append(f"[{h.get('hotel_id')}] {h.get('name')} | review={rs}")
                detail.append(f"    > {str(m)[:160].strip()}")
            detail.append("")
    return lines + ["", f"##################### {title}: DETAIL #####################"] + detail


def main():
    hotels = []
    with open(CORPUS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                hotels.append(json.loads(line))

    out = section(hotels, POLICY_THEMES, policy_match, "POLICY")
    out += ["", ""]
    out += section(hotels, AMENITY_THEMES, amenity_match, "AMENITY")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(f"Done. Report -> {OUT}")


if __name__ == "__main__":
    main()
