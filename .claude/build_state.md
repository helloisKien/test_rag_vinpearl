# Project State

## Goal
Xây walking skeleton chạy thật cho **SearchAPI (`POST /search`)** + **ContextAPI (`POST /context`)** end-to-end, đủ để:
1. 2 API hoạt động đúng thiết kế ([docs/VuDucKien_api_schema_proposal.md](../docs/VuDucKien_api_schema_proposal.md)).
2. Lấy **kết quả Evaluation thật** ([docs/VuDucKien_evaluation_plan ...](../docs/)).
3. Lấy **kết quả Monitoring thật** ([docs/VuDucKien_monitoring_plan ...](../docs/)).
Plan chi tiết: [docs/VuDucKien_build_plan.md](../docs/VuDucKien_build_plan.md). Code đặt ở gốc repo (cùng cấp `data/`, `ontology/`, `evaluation/`, `golden_dataset/`).

## Current Plan
**Phase 0 (Infra) + Phase 1 (Ingest):** code/config đã viết xong và đã validate offline.
Mục tiêu hiện tại: **xác minh Acceptance Criteria của Phase 0 & Phase 1 bằng command thật** (chưa chạy) trước khi sang Phase 2.

## Phase Progress
* [~] Phase 0 - Environment & Infra        — file đã tạo; ACCEPTANCE PENDING (chưa `docker compose up`)
* [~] Phase 1 - Ingest → PostgreSQL        — code xong + validate offline; ACCEPTANCE PENDING (chưa chạy ingest)
* [ ] Phase 2 - Chunking
* [ ] Phase 3 - Embedding + Indexing
* [ ] Phase 4 - Retrieval Core
* [ ] Phase 5 - Intent Parsing
* [ ] Phase 6 - SearchAPI
* [ ] Phase 7 - ContextAPI
* [ ] Phase 8 - Observability
* [ ] Phase 9 - Evaluation
* [ ] Phase 10 - Final Reports

## Completed
- **Phân tích & resolve conflict:** Decision Log R1–R18 trong build plan §1.
- **Golden set chuẩn hoá:** `golden_dataset/golden_set_v1.json` — 49 query, GT hotel đầy đủ (mean 13/query). Đã sửa 3 query (GS-FAQ-007/POL-001/POL-003) chuyển `suitable_for` hard→soft. Verify **635/635 GT reachable**. Backup: `golden_dataset/golden_set_v1.backup.json`.
- **Scaffold Phase 0 (file đã tạo):** `docker-compose.yml`, `requirements.txt`, `.env.example`, `.gitignore`, `db/schema.sql`, `config/settings.py`, `config/__init__.py`, `pipeline/__init__.py`, `observability/prometheus/prometheus.yml`, `README_BUILD.md`.
- **Phase 1 code:** `pipeline/ingest_db.py` — validate offline trên 520 file (helper chạy sạch, 0 lỗi): amenities flat 73.4 → UNION 75.0/hotel; rooms 4682, nearby 4991, activities 4560.

## Files Created Or Modified
- Created: `docker-compose.yml`, `requirements.txt`, `.env.example`, `.gitignore`, `README_BUILD.md`,
  `db/schema.sql`, `config/settings.py`, `config/__init__.py`, `pipeline/ingest_db.py`, `pipeline/__init__.py`,
  `observability/prometheus/prometheus.yml`, `.claude/build_state.md`.
- Modified: `golden_dataset/golden_set_v1.json` (backup `.backup.json`), `docs/VuDucKien_build_plan.md`.

## Architecture Decisions
- **R2** `hotel_id` = int Agoda ở mọi nơi.
- **R4** Chunk-text store = OpenSearch `_source`; Qdrant chỉ payload nhẹ. Bỏ bảng `text_chunks`.
- **R7** Pre-filter PostgreSQL-only (không Neo4j).
- **R14** policy = `secondary.hotel_policy.policyNotes`; `rooms.price = price_per_night`. Chunk policy lấy thêm từ `useful_info` + `faq` (đã lưu JSONB).
- **R17** `hotels.amenities` = UNION mọi field amenity (vá GS-AMEN-008). Đã verify.
- **R18** Amenity hard-filter ở mức CONCEPT (ontology synonym_dictionary) cho biến thể (GS-AMEN-009 non-smoking).
- **R15** Retrieve `top_k≥15` (đề xuất 20); report Recall@10 (primary) + Recall@15, MRR@10, NDCG@10.
- Ingest dùng **psycopg2** (sync) cho đơn giản; API sẽ dùng **asyncpg** (async). DDL idempotent + TRUNCATE để re-run.
- Code ở **gốc repo** (không nest `da10/`) để path tới `data/`, `ontology/`, `evaluation/`, `golden_dataset/` resolve trực tiếp.

## Commands Executed
*(Chưa có command runtime nào do người dùng chạy. Các script phân tích/validate do assistant chạy ở phiên trước chỉ đọc dữ liệu + sửa file, không dựng hạ tầng.)*
- PENDING: Phase 0 infra (`docker compose up -d`).
- PENDING: Phase 1 ingest (`python pipeline/ingest_db.py`).

## Issues
- Chưa rõ máy đã cài Docker + Python venv chưa (Open Questions).
- `policy_notes` thưa (avg 0.9/hotel) → Phase 2 chunk policy phải bổ sung từ `useful_info` + `faq`.

## Next Step
**Người dùng chạy command Phase 0 + Phase 1** (xem mục đề xuất command bên dưới trong chat) rồi gửi kết quả. Sau khi nhận:
- Nếu đạt acceptance (5 service healthy + hotels=520) → tick Phase 0,1 → sang **Phase 2 (Chunking)**.
- Nếu lỗi → ghi vào Issues + sửa.

## Open Questions
1. Máy đã có Docker Desktop chạy chưa?
2. Đã tạo Python venv + cài deps chưa? (Phase 1 chỉ cần `psycopg2-binary`, `pydantic-settings`; bản đầy đủ `requirements.txt` (torch/FlagEmbedding) để dành Phase 3.)
3. Có dùng GPU cho embedding (Phase 3) không, hay CPU?

## Session Summary
Đã hoàn tất phân tích, resolve conflict (R1–R18), chuẩn hoá golden set (635/635 GT reachable), và dựng scaffold + Phase 1 ingest (validate offline 0 lỗi). Đang chờ người dùng chạy command Phase 0 (docker) + Phase 1 (ingest) để xác minh acceptance trước khi sang Phase 2 (Chunking).
