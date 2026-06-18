import psycopg2
import sys, os
sys.path.insert(0, '.')
from config.settings import settings

conn = psycopg2.connect(settings.pg_dsn)
cur = conn.cursor()

print("=== Resort 5 sao Nha Trang ===")
cur.execute("""
    SELECT id, name, star_rating, accommodation_type
    FROM hotels
    WHERE city = 'Nha Trang' AND star_rating >= 5 AND accommodation_type = 'Resort'
""")
for row in cur.fetchall():
    print(row)

print("\n=== Amenities of hotel 805030 ===")
cur.execute("SELECT amenities FROM hotels WHERE id = 805030")
row = cur.fetchone()
if row:
    for a in row[0]:
        print(" -", a)

print("\n=== Bãi đỗ xe count (Nha Trang) ===")
cur.execute("""
    SELECT 
      COUNT(*) FILTER (WHERE amenities @> ARRAY['Bãi đỗ xe miễn phí']) as mien_phi,
      COUNT(*) FILTER (WHERE amenities @> ARRAY['Bãi đỗ xe']) as co_bai_do_xe
    FROM hotels WHERE city = 'Nha Trang'
""")
print(cur.fetchone())

cur.close()
conn.close()
