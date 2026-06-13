"""build_expansion.py — TỰ SINH query_expansion.yaml (Lớp A). Thay viết tay.

Owner: Trương Anh Long (KE, DA10). query_expansion (concept -> concept liên quan) trước đây
VIẾT TAY + đoán `domain` -> không scale, dễ sót. File này sinh TỰ ĐỘNG từ 2 nguồn DATA-DRIVEN:

  NGUỒN 1 — quan hệ ontology (related/broader/narrower trong core/*.yaml):
      cạnh người ĐÃ duyệt khi xây concept -> chắc chắn. source=ontology_relation.
  NGUỒN 2 — co-occurrence trong tag 520 hotel (hotel_tags.json, Bước 2):
      với cặp (A,B): P(B|A) = #hotel có cả A,B / #hotel có A. Nếu cao + đủ mẫu -> cạnh A->B.
      Đây là "đọc data" thật (bằng chứng thống kê), KHÔNG đoán. source=cooccurrence(p,n).

LỌC (tránh cạnh tầm thường / nhiễu):
  - chỉ sinh cạnh từ facet "ý định/bối cảnh" -> facet "tiện ích/đặc tính":
      purpose|style|setting|price_tier|object_type  ->  amenity|setting|style
    (vd "gia đình"->"kids club" hữu ích; "wifi"->"điều hòa" thì vô nghĩa -> bỏ).
  - bỏ self, bỏ cặp đã có từ nguồn 1 (ưu tiên ontology_relation).

KẾT QUẢ: mọi cạnh có `source` + bằng chứng. status=unverified (chờ golden set A/B — KHÔNG
tự coi là đã kiểm). Người chỉ DUYỆT danh sách máy đề xuất, không viết tay từ đầu.

Chạy: .venv/Scripts/python.exe -X utf8 -m knowledge_engineering.common.build_expansion
"""

from __future__ import annotations

import glob
import json
from collections import defaultdict

import yaml

CORE_GLOB = "ontology/core/*.yaml"
TAGS_JSON = "knowledge_engineering/enrichment/hotel_tags.json"
OUT_YAML = "ontology/query_expansion.yaml"

# Co-occurrence: ngưỡng giữ cạnh
COOC_MIN_PROB = 0.5     # P(B|A) >= 0.5 (B hay đi cùng A)
COOC_MIN_SUPPORT = 15   # ít nhất 15 hotel có A (đủ mẫu, tránh nhiễu)
COOC_MIN_LIFT = 1.3     # P(B|A)/P(B) >= 1.3 — B ĐẶC TRƯNG cho A, không phải B phổ biến khắp nơi.
                        # (Wifi/AC có ở ~mọi hotel -> lift≈1 -> LOẠI. kids_club hiếm nhưng cao
                        #  trong family -> lift cao -> GIỮ. Đây là chốt chặn "phổ biến ≠ liên quan".)
COOC_MAX_PER_CONCEPT = 5  # mỗi concept khóa giữ tối đa 5 cạnh mạnh nhất (theo lift)

# Facet được phép làm KHÓA (vế trái) và ĐÍCH (vế phải) của expansion
SRC_FACETS = {"purpose", "style", "setting", "price_tier", "object_type", "location"}
DST_FACETS = {"amenity", "setting", "style"}


def load_concept_facets() -> dict[str, str]:
    out = {}
    for f in sorted(glob.glob(CORE_GLOB)):
        d = yaml.safe_load(open(f, encoding="utf-8")) or {}
        for cid, v in (d.get("concepts") or {}).items():
            out[cid] = v.get("facet", "")
    return out


def from_ontology_relations() -> dict[str, dict]:
    """NGUỒN 1: related/broader/narrower -> cạnh expansion. Trả {cid: {expands_to:set, source}}."""
    rules: dict[str, set] = defaultdict(set)
    for f in sorted(glob.glob(CORE_GLOB)):
        if "generated" in f:
            continue
        d = yaml.safe_load(open(f, encoding="utf-8")) or {}
        for cid, v in (d.get("concepts") or {}).items():
            for key in ("related", "broader", "narrower"):
                r = v.get(key)
                if not r:
                    continue
                for tgt in (r if isinstance(r, list) else [r]):
                    if tgt != cid:
                        rules[cid].add(tgt)
    return rules


def from_cooccurrence(facets: dict[str, str]) -> dict[str, list[tuple]]:
    """NGUỒN 2: co-occurrence trong tag. Trả {cid: [(tgt, prob, support), ...]}."""
    import os
    if not os.path.exists(TAGS_JSON):
        return {}
    tags = json.load(open(TAGS_JSON, encoding="utf-8"))
    # đếm xuất hiện + đồng xuất hiện
    cnt: dict[str, int] = defaultdict(int)
    co: dict[tuple, int] = defaultdict(int)
    for tl in tags.values():
        concepts = {t["concept"] for t in tl}
        for a in concepts:
            cnt[a] += 1
        for a in concepts:
            for b in concepts:
                if a != b:
                    co[(a, b)] += 1

    n_hotels = len(tags)
    out: dict[str, list[tuple]] = defaultdict(list)
    for (a, b), n_ab in co.items():
        fa, fb = facets.get(a, ""), facets.get(b, "")
        if fa not in SRC_FACETS or fb not in DST_FACETS:
            continue
        if cnt[a] < COOC_MIN_SUPPORT:
            continue
        prob = n_ab / cnt[a]                       # P(B|A)
        base = cnt[b] / n_hotels                   # P(B) — mức nền của B
        lift = prob / base if base > 0 else 0      # B đặc trưng cho A tới đâu
        if prob >= COOC_MIN_PROB and lift >= COOC_MIN_LIFT:
            out[a].append((b, round(prob, 2), cnt[a], round(lift, 2)))
    # mỗi concept giữ top cạnh theo LIFT (đặc trưng nhất), không theo prob (phổ biến nhất)
    for a in out:
        out[a].sort(key=lambda x: -x[3])
        out[a] = out[a][:COOC_MAX_PER_CONCEPT]
    return out


def build() -> dict:
    facets = load_concept_facets()
    rel = from_ontology_relations()
    cooc = from_cooccurrence(facets)

    rules: dict[str, dict] = {}
    all_keys = set(rel) | set(cooc)
    for cid in sorted(all_keys):
        expands: dict[str, dict] = {}
        # nguồn 1 (ưu tiên): ontology_relation
        for tgt in sorted(rel.get(cid, set())):
            expands[tgt] = {"source": "ontology_relation"}
        # nguồn 2: cooccurrence (không ghi đè nguồn 1)
        for tgt, prob, sup, lift in cooc.get(cid, []):
            if tgt not in expands:
                expands[tgt] = {"source": f"cooccurrence(p={prob},lift={lift},n={sup})"}
        if expands:
            rules[cid] = {
                "expands_to": sorted(expands),
                "evidence": {t: expands[t]["source"] for t in sorted(expands)},
                "status": "unverified",
            }
    return rules


def write() -> tuple[int, int]:
    rules = build()
    n_edges = sum(len(r["expands_to"]) for r in rules.values())
    header = (
        "# AUTO-GENERATED — KHÔNG sửa tay. Sinh bởi "
        "knowledge_engineering/common/build_expansion.py\n"
        "# Nguồn: (1) related/broader/narrower trong ontology/core (ontology_relation);\n"
        "#        (2) co-occurrence trong hotel_tags.json (cooccurrence(p,n)).\n"
        "# status=unverified: CHỜ golden set A/B. KHÔNG dùng như đã kiểm chứng.\n"
        "# Bàn giao -> Anh Tài (áp dụng lúc query). Đổi corpus/concept -> chạy lại script.\n"
    )
    with open(OUT_YAML, "w", encoding="utf-8") as fh:
        fh.write(header)
        yaml.safe_dump(
            {"version": "3.0.0", "status": "unverified",
             "default_weight": 0.5, "rules": rules},
            fh, allow_unicode=True, sort_keys=False,
        )
    return len(rules), n_edges


if __name__ == "__main__":
    n_rules, n_edges = write()
    print(f"Đã sinh {n_rules} concept khóa, {n_edges} cạnh expansion -> {OUT_YAML}")
