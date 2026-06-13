"""
find_faq_act_candidates_v2.py
-----------------------------
Tổng hợp ứng viên cho Golden query (FAQ + ACTIVITY), chọn theo tiêu chí >=5 ứng viên/city.

Cách chạy (từ d:\\Test):
    python evaluation/tools/find_faq_act_candidates_v2.py

Output:
    evaluation/tools/faq_act_candidates_v2.txt
"""

import json
import os
import unicodedata
from collections import defaultdict

CORPUS = os.path.join(os.path.dirname(__file__), "..", "corpus", "faq_activities_corpus.jsonl")
OUT = os.path.join(os.path.dirname(__file__), "faq_act_candidates_v2.txt")


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D").lower()


# FAQ labels: (label, category_substr, answer_keywords[])  (kws=[] -> chỉ cần đúng category)
FAQ_LABELS = [
    ("parking",        "facilities_parking", []),
    ("laundry",        "facilities_cleaning", ["giat"]),
    ("payment",        "info_payment", []),
    ("shuttle",        "", ["dua don san bay"]),
    ("spa",            "things-to-do", ["spa"]),
    ("pool",           "things-to-do", ["be boi", "ho boi"]),
    ("bar",            "facilities_food and drink", ["bar"]),
    ("family",         "policies_family", []),
    ("price",          "info_price", []),
    ("year_built",     "info_property", ["xay dung"]),
    ("languages",      "languages spoken", []),
]


def faq_match(h, cat, kws):
    for fq in h.get("faq") or []:
        if cat and cat.lower() not in (fq.get("cat") or "").lower():
            continue
        ans_n = norm(fq.get("a"))
        if not kws or any(k in ans_n for k in kws):
            return fq
    return None


def faq_section(hotels):
    lines = ["##################### FAQ: MATRIX (category x city, count>=5) #####################"]
    detail = []
    for label, cat, kws in FAQ_LABELS:
        by_city = defaultdict(list)
        for h in hotels:
            fq = faq_match(h, cat, kws)
            if fq:
                by_city[h.get("city") or "?"].append((h.get("review_score") or 0, h, fq))
        good = {c: v for c, v in by_city.items() if len(v) >= 5}
        lines.append(f"\n### FAQ label='{label}' (cat~'{cat}', kws={kws})")
        for c, v in sorted(good.items(), key=lambda x: -len(x[1])):
            lines.append(f"    {len(v):3d}  {c}")
        # detail cho 3 city nhiều nhất
        for c, v in sorted(good.items(), key=lambda x: -len(x[1]))[:3]:
            v.sort(key=lambda x: x[0], reverse=True)
            detail.append("=" * 90)
            detail.append(f"FAQ '{label}' | city={c} | n={len(v)}")
            detail.append("=" * 90)
            for rs, h, fq in v[:8]:
                detail.append(f"[{h.get('hotel_id')}] {h.get('name')} | review={rs}")
                detail.append(f"    Q: {fq.get('q')}")
                detail.append(f"    A: {(fq.get('a') or '')[:160].strip()}")
            detail.append("")
    return lines + ["", "##################### FAQ: DETAIL #####################"] + detail


# ACTIVITY themes: (label, city_substr, kws[])
ACT_THEMES = [
    ("vinwonders_nhatrang", "Nha Trang", ["vinwonders", "vinpearl harbour", "vinke"]),
    ("cruise_halong",       "Hạ Long",   ["du thuyen", "cruise", "vinh ha long", "kayak"]),
    ("bana_danang",         "Đà Nẵng",   ["ba na", "bana", "sun world ba na", "cap treo"]),
    ("basketboat_hoian",    "Hội An",    ["thung", "rung dua", "coconut", "bay mau"]),
    ("coaster_dalat",       "Đà Lạt",    ["alpine", "coaster", "datanla", "truot"]),
    ("phuquoc_park",        "Phú Quốc",  ["vinwonders", "grand world", "hon thom", "safari"]),
    ("show_hanoi",          "Hà Nội",    ["roi nuoc", "puppet", "thang long"]),
    ("hue_tour",            "Huế",       ["song huong", "dai noi", "ca hue", "citadel", "city tour"]),
    ("hotspring_danang",    "Đà Nẵng",   ["than tai", "suoi khoang", "khoang nong"]),
    ("ninhbinh_from_hanoi", "Hà Nội",    ["trang an", "ninh binh", "tam coc", "bai dinh", "hoa lu"]),
    ("fasttrack_hcm",       "Hồ Chí Minh", ["fast track", "fast-track", "lounge", "phong cho", "don tien san bay"]),
]


def act_section(hotels):
    lines = ["##################### ACTIVITY THEMES (top 8/city) #####################"]
    for label, city, kws in ACT_THEMES:
        cands = []
        for h in hotels:
            if norm(city) not in norm(h.get("city") or ""):
                continue
            hits = []
            for act in h.get("activities") or []:
                blob = norm(act.get("title")) + " " + norm(act.get("desc"))
                if any(k in blob for k in kws):
                    hits.append(act.get("title", ""))
            if hits:
                cands.append((len(hits), h.get("review_score") or 0, h, hits))
        cands.sort(key=lambda x: (x[0], x[1]), reverse=True)
        lines.append("=" * 90)
        lines.append(f"ACT '{label}' | city~{city} | kws={kws} | matched={len(cands)}")
        lines.append("=" * 90)
        for n, rs, h, hits in cands[:8]:
            lines.append(f"[{h.get('hotel_id')}] {h.get('name')} | {h.get('city')} | review={rs} | hits={n}")
            for t in hits[:2]:
                lines.append(f"    - {t}")
        lines.append("")
    return lines


def main():
    hotels = []
    with open(CORPUS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                hotels.append(json.loads(line))

    out = faq_section(hotels) + ["", ""] + act_section(hotels)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(f"Done. Report -> {OUT}")


if __name__ == "__main__":
    main()
