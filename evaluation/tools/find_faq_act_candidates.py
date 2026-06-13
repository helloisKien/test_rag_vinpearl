"""
find_faq_act_candidates.py
--------------------------
Quét faq_activities_corpus.jsonl để tìm ứng viên cho 2 nhóm Golden query:
  - FAQ themes      : câu trả lời nằm trong phần `faq`
  - ACTIVITY themes : câu trả lời nằm trong phần `activities`

Mỗi theme gắn 1 city cụ thể. In ra báo cáo (tên KS, review, snippet) để gán nhãn.

Cách chạy (từ d:\\Test):
    python evaluation/tools/find_faq_act_candidates.py

Output:
    evaluation/tools/faq_act_candidates_report.txt
"""

import json
import os
import unicodedata

CORPUS = os.path.join(os.path.dirname(__file__), "..", "corpus", "faq_activities_corpus.jsonl")
OUT = os.path.join(os.path.dirname(__file__), "faq_act_candidates_report.txt")


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D").lower()


# FAQ themes: (id, city_substr, category_substr, [answer_keywords_norm])
# answer_keywords để lọc câu trả lời khẳng định (có dịch vụ). Để [] = chỉ cần đúng category.
FAQ_THEMES = [
    ("FAQ1_airport_shuttle", "Đà Nẵng", "location_airport", ["dua don", "don tien", "xe dua"]),
    ("FAQ2_parking",         "Nha Trang", "facilities_parking", []),
    ("FAQ3_laundry",         "Hà Nội", "facilities_cleaning", ["giat"]),
    ("FAQ4_family_child",    "Đà Lạt", "policies_family", []),
    ("FAQ5_payment_cashless","Hồ Chí Minh", "info_payment", []),
    ("FAQ6_spa",             "Phú Quốc", "things-to-do", ["spa"]),
    ("FAQ7_bar",             "Hạ Long", "food and drink", ["bar", "quay bar", "do uong"]),
    ("FAQ8_languages",       "Huế", "languages spoken", []),
    ("FAQ9_getting_around",  "Hội An", "getting around", []),
    ("FAQ10_pool",           "Vũng Tàu", "things-to-do", ["be boi", "ho boi", "boi"]),
]

# Activity themes: (id, city_substr, [title/desc keywords_norm])
ACT_THEMES = [
    ("ACT1_vinwonders_nhatrang", "Nha Trang", ["vinwonders", "vinpearl", "vinke"]),
    ("ACT2_cruise_halong",       "Hạ Long", ["du thuyen", "cruise", "vinh", "kayak"]),
    ("ACT3_bana_danang",         "Đà Nẵng", ["ba na", "bana", "sun world", "cap treo"]),
    ("ACT4_basketboat_hoian",    "Hội An", ["thung", "rung dua", "coconut", "bay mau"]),
    ("ACT5_coaster_dalat",       "Đà Lạt", ["alpine", "coaster", "mang truot", "datanla", "truot"]),
    ("ACT6_phuquoc_park",        "Phú Quốc", ["vinwonders", "grand world", "hon thom", "cap treo", "safari"]),
    ("ACT7_show_hanoi",          "Hà Nội", ["roi nuoc", "show", "city tour", "lang"]),
    ("ACT8_sapa_trek",           "Sa Pa", ["sapa", "fansipan", "trek", "cap treo"]),
    ("ACT9_hue_tour",            "Huế", ["song huong", "dai noi", "lang", "thuyen rong", "city tour"]),
    ("ACT10_quynhon_kyco",       "Quy Nhơn", ["ky co", "eo gio", "cu lao", "lan bien", "cano"]),
]


def main():
    hotels = []
    with open(CORPUS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                hotels.append(json.loads(line))

    lines = []

    lines.append("##################### FAQ THEMES #####################")
    for tid, city, cat, kws in FAQ_THEMES:
        cands = []
        for h in hotels:
            if norm(city) not in norm(h.get("city") or ""):
                continue
            matched = None
            for fq in h.get("faq") or []:
                if cat.lower() in (fq.get("cat") or "").lower():
                    ans_n = norm(fq.get("a"))
                    if not kws or any(k in ans_n for k in kws):
                        matched = fq
                        break
            if matched:
                cands.append((h.get("review_score") or 0, h, matched))
        cands.sort(key=lambda x: x[0], reverse=True)

        lines.append("=" * 90)
        lines.append(f"{tid} | city~{city} | cat~{cat} | kws={kws} | matched={len(cands)}")
        lines.append("=" * 90)
        for rs, h, fq in cands[:10]:
            ans = (fq.get("a") or "").replace("\n", " ")
            lines.append(f"[{h.get('hotel_id')}] {h.get('name')} | {h.get('city')} | review={rs}")
            lines.append(f"    Q: {fq.get('q')}")
            lines.append(f"    A: {ans[:180]}")
        lines.append("")

    lines.append("")
    lines.append("##################### ACTIVITY THEMES #####################")
    for tid, city, kws in ACT_THEMES:
        cands = []
        for h in hotels:
            if norm(city) not in norm(h.get("city") or ""):
                continue
            hit_titles = []
            for act in h.get("activities") or []:
                blob = norm(act.get("title")) + " " + norm(act.get("desc"))
                if any(k in blob for k in kws):
                    hit_titles.append(act.get("title", ""))
            if hit_titles:
                cands.append((len(hit_titles), h.get("review_score") or 0, h, hit_titles))
        cands.sort(key=lambda x: (x[0], x[1]), reverse=True)

        lines.append("=" * 90)
        lines.append(f"{tid} | city~{city} | kws={kws} | matched={len(cands)}")
        lines.append("=" * 90)
        for n, rs, h, titles in cands[:10]:
            lines.append(f"[{h.get('hotel_id')}] {h.get('name')} | {h.get('city')} | review={rs} | n_act_hit={n}")
            for t in titles[:3]:
                lines.append(f"    - {t}")
        lines.append("")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Done. Report -> {OUT}")


if __name__ == "__main__":
    main()
