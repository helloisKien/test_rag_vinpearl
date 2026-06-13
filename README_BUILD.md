# DA10 — Build Runbook (SearchAPI + ContextAPI)

> Plan chi tiết: [docs/VuDucKien_build_plan.md](docs/VuDucKien_build_plan.md). File này = quickstart vận hành.
> Code đặt ở **gốc repo** (cùng cấp `data/`, `ontology/`, `evaluation/`, `golden_dataset/`) để path resolve trực tiếp.

## Cấu trúc hiện có
```
docker-compose.yml      # Phase 0 — postgres, opensearch, qdrant, prometheus, grafana
requirements.txt        # deps đã pin
.env.example            # copy -> .env
db/schema.sql           # DDL 4 bảng (R2 int id, R17 amenities union)
config/settings.py      # đọc .env
pipeline/ingest_db.py   # ✅ Phase 1 — READY, đã validate offline trên 520 file
observability/prometheus/prometheus.yml
data/ ontology/ evaluation/corpus/ golden_dataset/   # đã có sẵn
```

## Trạng thái
| Phase | Trạng thái |
|---|---|
| 0 — Infra | scaffold xong; cần `docker compose up -d` |
| 1 — Ingest Postgres | ✅ **code xong & validated** (`pipeline/ingest_db.py`) |
| 2 — Chunking | TODO (`pipeline/chunking.py`) — input `evaluation/corpus/*.jsonl` |
| 3 — Embed + Index | TODO (`pipeline/embed.py`, `pipeline/index.py`) |
| 4 — Retrieval | TODO (`core/`) |
| 5 — Intent | TODO (`core/intent.py`) — nạp `ontology/` |
| 6 — SearchAPI | TODO (`api/main.py`) |
| 7 — ContextAPI | TODO (`core/context.py`) |
| 8 — Observability | TODO (`observability/`) |
| 9 — run_eval | TODO (`evaluation/run_eval.py`) — golden set GT đã đầy đủ |
| 10 — Reports | TODO |

## Chạy Phase 0–1 ngay
```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r requirements.txt

copy .env.example .env            # Windows (cp trên *nix)

docker compose up -d              # đợi postgres healthy
python pipeline/ingest_db.py      # -> ✓ 520 hotels, ~4682 rooms, ~4991 nearby, ~4560 activities
```
Kiểm tra:
```bash
docker compose exec postgres psql -U da10 -d da10 -c "SELECT count(*) FROM hotels;"
docker compose exec postgres psql -U da10 -d da10 -c "SELECT id,city,array_length(amenities,1) FROM hotels LIMIT 5;"
```

## Quyết định đã đóng băng (xem Decision Log build plan §1)
- **R2** hotel_id = int Agoda. **R17** `hotels.amenities` = UNION mọi field amenity (vá GS-AMEN-008).
- **R18** amenity hard-filter ở **mức concept** (synonym_dictionary) cho biến thể (GS-AMEN-009 non-smoking).
- **R14** policy = `secondary.hotel_policy.policyNotes`; `rooms.price = price_per_night`. (Chunk policy còn lấy thêm từ `useful_info` + `faq` category policy — đã lưu JSONB.)
- **Golden set** `golden_dataset/golden_set_v1.json`: 49 query, GT hotel đầy đủ (mean 13/query), **635/635 GT reachable** dưới luật filter cuối. 3 query (GS-FAQ-007/POL-001/POL-003) đã chuyển `suitable_for` hard→soft (backup: `golden_set_v1.backup.json`).
- **R15** retrieve `top_k≥15` (đề xuất 20); report Recall@10 (primary) + Recall@15, MRR@10, NDCG@10.

## Còn chờ team (không block walking skeleton)
- `relevant_chunk_ids` trong golden set (điền sau Phase 3 khi có chunk v1).
- Bản chunking/index thật của Khánh Duy/Đạt + SearchEngine của Anh Tài (swap theo seam — build plan §7).
