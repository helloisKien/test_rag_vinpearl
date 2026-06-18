"""Sinh thống kê domain cho domain_analysis.md — Lớp A (regenerate khi corpus đổi).

Quét data/raw/hotels/*.json -> tính các bảng thống kê -> (1) ghi domain_stats.json (dữ liệu),
(2) render các bảng vào domain_analysis.md GIỮA MARKER (giữ phần văn xuôi phân tích nguyên vẹn).

Marker trong domain_analysis.md:
    <!-- AUTO-STATS:<id>:START -->
    ...nội dung do script sinh, KHÔNG sửa tay...
    <!-- AUTO-STATS:<id>:END -->

Khi corpus mở rộng (51 -> 500-1000): chạy lại 1 lệnh, số liệu trong domain_analysis.md tự cập nhật.

Chạy: .venv/Scripts/python.exe -X utf8 -m knowledge_engineering.entity_extraction.build_domain_stats
"""

import glob
import json
import re
from collections import Counter

HOTELS_GLOB = "data/raw/hotels/*.json"
STATS_JSON = "docs2/reports/ontology/sprint1/domain_stats.json"
DOMAIN_MD = "docs2/reports/ontology/sprint1/domain_analysis.md"


def compute_stats(hotels_glob: str = HOTELS_GLOB) -> dict:
    files = sorted(glob.glob(hotels_glob))
    n = len(files)
    acc = Counter(); prop = Counter(); star = Counter(); city = Counter()
    suitable = Counter(); views = Counter(); tags = Counter()
    rtags = Counter(); nbtype = Counter()
    for f in files:
        d = json.load(open(f, encoding="utf-8"))
        acc[d.get("accommodation_type")] += 1
        prop[d.get("property_type")] += 1
        star[d.get("star_rating")] += 1
        city[d.get("city")] += 1
        for x in d.get("suitable_for") or []:
            suitable[x] += 1
        for x in d.get("view_types") or []:
            views[x] += 1
        for x in set(d.get("tags") or []):
            tags[x] += 1
        rd = d.get("reviews_detail") or {}
        for t in rd.get("tags") or []:
            nm = t.get("tag")
            if nm:
                rtags[nm] += 1
        for p in d.get("nearby_places") or []:
            nbtype[p.get("type")] += 1
    return {
        "n_hotels": n,
        "accommodation_type": acc.most_common(),
        "property_type": prop.most_common(),
        "star_rating": star.most_common(),
        "city": city.most_common(),
        "suitable_for": suitable.most_common(),
        "view_types": views.most_common(),
        "tags": tags.most_common(),
        "review_tags": rtags.most_common(),
        "nearby_type": nbtype.most_common(),
    }


def _fmt(pairs, top=None, sep=", "):
    items = pairs[:top] if top else pairs
    return sep.join(f"{k} ({v})" for k, v in items)


def render_blocks(s: dict) -> dict[str, str]:
    """id -> markdown content (đặt giữa marker). Chỉ phần số liệu thuần."""
    n = s["n_hotels"]
    city_top = _fmt(s["city"], top=8)
    n_city_one = sum(1 for _, v in s["city"] if v == 1)

    corpus = (
        "| Chiều | Giá trị nguồn (Agoda) → số hotel |\n"
        "|---|---|\n"
        f"| `accommodation_type` | {_fmt(s['accommodation_type'])} |\n"
        f"| `property_type` | {_fmt(s['property_type'])} |\n"
        f"| `star_rating` | {_fmt(s['star_rating'])} |\n"
        f"| `city` ({len(s['city'])} nơi) | {city_top}"
        f"{f', + {n_city_one} tỉnh/thành mỗi nơi 1' if n_city_one else ''} |"
    )

    suitable = "- " + " · ".join(f"{k} ({v})" for k, v in s["suitable_for"])
    views = "- " + " · ".join(f"{k} ({v})" for k, v in s["view_types"][:12])
    rtags = "- " + " · ".join(f"{k} ({v})" for k, v in s["review_tags"][:20])
    nearby = (
        f"Nhiều nhất: {_fmt(s['nearby_type'], top=10)}...\n"
        "→ Mỗi `nearby_places` có `distance_km` → chuẩn hóa thẳng vào quan hệ `near` (Task 1.5)."
    )

    return {
        "corpus": corpus,
        "suitable_for": suitable,
        "view_types": views,
        "review_tags": rtags,
        "nearby_type": nearby,
    }


def inject_markers(md_path: str, blocks: dict[str, str]) -> list[str]:
    """Thay nội dung giữa marker cho từng id. Trả list id đã thay."""
    txt = open(md_path, encoding="utf-8").read()
    replaced = []
    for bid, content in blocks.items():
        pat = re.compile(
            r"(<!-- AUTO-STATS:" + re.escape(bid) + r":START -->\n).*?(\n<!-- AUTO-STATS:"
            + re.escape(bid) + r":END -->)",
            re.S,
        )
        if pat.search(txt):
            txt = pat.sub(lambda m: m.group(1) + content + m.group(2), txt)
            replaced.append(bid)
    open(md_path, "w", encoding="utf-8").write(txt)
    return replaced


if __name__ == "__main__":
    s = compute_stats()
    json.dump(s, open(STATS_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    blocks = render_blocks(s)
    replaced = inject_markers(DOMAIN_MD, blocks)
    print(f"n_hotels={s['n_hotels']} -> {STATS_JSON}")
    print(f"Đã render {len(replaced)} block vào {DOMAIN_MD}: {replaced}")
    missing = [b for b in blocks if b not in replaced]
    if missing:
        print(f"⚠ Chưa có marker cho: {missing} (thêm marker vào .md nếu muốn auto)")
