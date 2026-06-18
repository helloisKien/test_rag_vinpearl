"""DA10 — Phase 4: SQL pre-filter (R7 PostgreSQL-only).

sql_whitelist(filters) -> set[int] hotel_id thoả hard filters, hoặc None nếu KHÔNG có
filter cứng nào (=> tìm trên toàn corpus). set rỗng => không hotel nào thoả (zero-result).

Hard filters hỗ trợ (R8 superset): city, accommodation_type, star_rating{min,max},
review_score{min}, suitable_for[], amenities[], price{min,max}.
amenities = exact-match AND (@>) — đủ cho 9/10 nhóm AMEN sau union ingest (R17).
GS-AMEN-009 (biến thể non-smoking) sẽ refine bằng concept-expansion sau (R18) — TODO.
"""
from __future__ import annotations
import psycopg2

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config.settings import settings  # noqa: E402


def sql_whitelist(filters, conn=None):
    filters = filters or {}
    conds, params = [], []

    if filters.get("city"):
        conds.append("h.city = %s"); params.append(filters["city"])

    acc = filters.get("accommodation_type")
    if acc:
        conds.append("h.accommodation_type = ANY(%s)"); params.append(list(acc))

    sr = filters.get("star_rating") or {}
    if sr.get("min") is not None:
        conds.append("h.star_rating >= %s"); params.append(sr["min"])
    if sr.get("max") is not None:
        conds.append("h.star_rating <= %s"); params.append(sr["max"])

    rv = filters.get("review_score") or {}
    if rv.get("min") is not None:
        conds.append("h.review_score >= %s"); params.append(rv["min"])

    suit = filters.get("suitable_for")
    if suit:
        conds.append("h.suitable_for && %s"); params.append(list(suit))   # OR overlap

    amen = filters.get("amenities")
    if amen:
        conds.append("h.amenities && %s"); params.append(list(amen))      # OR overlaps (any match)

    pr = filters.get("price") or {}
    if pr.get("min") is not None or pr.get("max") is not None:
        lo = pr.get("min") if pr.get("min") is not None else 0
        hi = pr.get("max") if pr.get("max") is not None else 10**12
        conds.append("EXISTS (SELECT 1 FROM rooms r WHERE r.hotel_id = h.id AND r.price BETWEEN %s AND %s)")
        params += [lo, hi]

    if not conds:
        return None  # không filter cứng => toàn corpus

    sql = "SELECT h.id FROM hotels h WHERE " + " AND ".join(conds)
    own = conn is None
    conn = conn or psycopg2.connect(settings.pg_dsn)
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        ids = {row[0] for row in cur.fetchall()}
        cur.close()
    finally:
        if own:
            conn.close()
    return ids
