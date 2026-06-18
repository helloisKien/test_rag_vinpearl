"""DA10 — Phase 2: Chunking. data/hotel_*.json -> chunks.jsonl.

Sinh chunk theo loại nguồn (build plan §Phase 2), chunk_id chuẩn (§3.2), payload (§3.3).
Standalone: chỉ cần stdlib (không cần DB, không cần torch). Đọc data/ trực tiếp cho giàu.

chunk_id = chunk-{hotel_id}-{source_code}-{seq:03d}
  desc/amen/faq/policy/review : source_code = type ; seq = chỉ số mảnh (1..)
  room/near/act               : source_code = type-{record_id} ; seq = 1 (+ tách nếu dài)

payload mỗi chunk: chunk_id, hotel_id, source_type, source_table, source_column, record_id,
                   lang, text (RAW để cite/trả), embed_text (context_prefix + text, để BM25+vector),
                   city, accommodation_type, star_rating.

Chạy:  python pipeline/chunking.py   ->  chunks.jsonl
"""
from __future__ import annotations
import glob
import json
import os
import re
import sys

DATA_DIR = "data"
OUT = "chunks.jsonl"
AMENITY_FIELDS = ["amenities", "amenities_general", "amenities_leisure", "amenities_dining"]
DESC_MAX_CHARS = 1000        # ~300 token VI; tách câu
REVIEW_CAP = 8               # số review/khách sạn (golden_set_v1 không có nhóm review)


# ----------------------------- helpers --------------------------------------
def str_list(v):
    if not v:
        return []
    if isinstance(v, str):
        v = [v]
    return [str(x).strip() for x in v if x is not None and str(x).strip()]


def amenities_union(d):
    s = set()
    for f in AMENITY_FIELDS:
        s |= set(str_list(d.get(f)))
    ag = d.get("amenity_groups") or {}
    if isinstance(ag, dict):
        for v in ag.values():
            if isinstance(v, list):
                s |= set(str_list(v))
    return sorted(s)


def to_float(v):
    try:
        return float(str(v).replace(",", ".")) if v not in (None, "") else None
    except (ValueError, TypeError):
        return None


def split_sentences(text, max_chars=DESC_MAX_CHARS):
    """Tách văn xuôi dài thành mảnh ~max_chars theo ranh giới câu."""
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    parts = re.split(r"(?<=[.!?…])\s+", text)
    chunks, buf = [], ""
    for p in parts:
        if len(buf) + len(p) + 1 > max_chars and buf:
            chunks.append(buf.strip())
            buf = p
        else:
            buf = f"{buf} {p}".strip()
    if buf:
        chunks.append(buf.strip())
    return chunks


def prefix(name, section):
    return f"{name} — {section}. "


def make(out, hid, base, code, seq, source_type, table, column, record_id, section, text, hotel):
    text = (text or "").strip()
    if not text:
        return
    cid = f"chunk-{hid}-{code}-{seq:03d}"
    pre = prefix(base["name"], section)
    out.append({
        "chunk_id": cid,
        "hotel_id": hid,
        "source_type": source_type,
        "source_table": table,
        "source_column": column,
        "record_id": record_id,
        "lang": "vi",
        "text": text,
        "embed_text": pre + text,
        "city": hotel.get("city"),
        "accommodation_type": hotel.get("accommodation_type"),
        "star_rating": to_float(hotel.get("star_rating")),
    })


# ----------------------------- chunk 1 hotel --------------------------------
def chunk_hotel(d):
    hid = int(d["hotel_id"])
    name = d.get("name") or f"Hotel {hid}"
    base = {"name": name}
    out = []

    # desc (recursive)
    for i, piece in enumerate(split_sentences(d.get("description")), 1):
        make(out, hid, base, "desc", i, "hotel_description", "hotels", "description", None,
             "Mô tả", piece, d)

    # amenity (whole)
    amen = amenities_union(d)
    if amen:
        make(out, hid, base, "amen", 1, "amenity", "hotels", "amenities", None,
             "Tiện nghi", "Tiện nghi: " + ", ".join(amen), d)

    # rooms (atomic)
    for r in d.get("rooms") or []:
        rid = r.get("room_type_id")
        parts = [r.get("name")]
        if r.get("room_size"):
            parts.append(f"diện tích {r['room_size']}")
        if r.get("bed_type") or r.get("bed_types"):
            parts.append("giường " + (r.get("bed_type") or "; ".join(str_list(r.get("bed_types")))))
        if r.get("room_view"):
            parts.append(f"hướng {r['room_view']}")
        if r.get("max_occupancy"):
            parts.append(f"tối đa {r['max_occupancy']} khách")
        ra = str_list(r.get("room_amenities"))
        if ra:
            parts.append("tiện nghi phòng: " + ", ".join(ra))
        txt = ". ".join(p for p in parts if p)
        make(out, hid, base, f"room-{rid}", 1, "room_info", "rooms", "name", rid,
             "Phòng", txt, d)

    # nearby (atomic)
    for i, p in enumerate(d.get("nearby_places") or []):
        dist = p.get("distance_km")
        txt = f"{p.get('name')} ({p.get('type')})" + (f" — cách {dist} km" if dist is not None else "")
        make(out, hid, base, f"near-{i}", 1, "nearby", "nearby_places", "name", i,
             "Địa điểm lân cận", txt, d)

    # activities (atomic)
    for a in d.get("activities") or []:
        aid = a.get("activity_id")
        txt = ". ".join(x for x in [a.get("title"), a.get("description")] if x)
        make(out, hid, base, f"act-{aid}", 1, "activity", "activities", "title", aid,
             "Hoạt động", txt, d)

    # faq (atomic)
    for i, f in enumerate(d.get("faq") or [], 1):
        q, ans = f.get("question"), f.get("answer")
        txt = ". ".join(x for x in [q, ans] if x)
        make(out, hid, base, "faq", i, "faq", "hotels", "faq", i - 1,
             "Câu hỏi thường gặp", txt, d)

    # policy (atomic): secondary.hotel_policy.policyNotes + useful_info
    seq = 1
    pol = ((d.get("secondary") or {}).get("hotel_policy") or {}).get("policyNotes") or []
    for note in str_list(pol):
        make(out, hid, base, "policy", seq, "policy", "hotels", "policy_notes", seq - 1,
             "Chính sách", note, d)
        seq += 1
    ui = d.get("useful_info") or {}
    if isinstance(ui, dict):
        for k, v in ui.items():
            if v in (None, "", []):
                continue
            make(out, hid, base, "policy", seq, "policy", "hotels", "useful_info", seq - 1,
                 "Thông tin hữu ích", f"{k}: {v}", d)
            seq += 1

    # review (atomic, optional) — từ sample_comments
    rd = d.get("reviews_detail") or {}
    for i, c in enumerate(rd.get("sample_comments") or [], 1):
        if i > REVIEW_CAP:
            break
        bits = [c.get("title"), c.get("text"), c.get("positives"), c.get("negatives"), c.get("response")]
        txt = ". ".join(str(x).strip() for x in bits if x)
        make(out, hid, base, "review", i, "review", "hotels", "reviews_detail", i - 1,
             "Đánh giá khách", txt, d)

    return out


# ----------------------------- run ------------------------------------------
def run():
    files = sorted(glob.glob(os.path.join(DATA_DIR, "hotel_*.json")))
    if not files:
        sys.exit(f"Không thấy {DATA_DIR}/hotel_*.json")

    from collections import Counter
    by_type = Counter()
    seen = set()
    dup = 0
    n = 0
    with open(OUT, "w", encoding="utf-8") as fh:
        for fp in files:
            d = json.load(open(fp, encoding="utf-8"))
            try:
                int(d["hotel_id"])
            except (KeyError, ValueError, TypeError):
                continue
            for ch in chunk_hotel(d):
                if ch["chunk_id"] in seen:
                    dup += 1
                    continue
                seen.add(ch["chunk_id"])
                by_type[ch["source_type"]] += 1
                fh.write(json.dumps(ch, ensure_ascii=False) + "\n")
                n += 1

    print(f"✓ Chunking xong: {n} chunks -> {OUT}  (dup bỏ qua: {dup})")
    for t, c in by_type.most_common():
        print(f"    {t:18s} {c}")
    # acceptance: hotel 805030 có các loại chunk
    sample = [cid for cid in seen if cid.startswith("chunk-805030-")]
    types805 = sorted({cid.split("-")[2] for cid in sample})
    print(f"  hotel 805030: {len(sample)} chunks, loại source_code: {types805}")


if __name__ == "__main__":
    run()
