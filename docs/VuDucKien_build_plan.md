# DA10 — Build Plan: SearchAPI + ContextAPI End-to-End (self-build, Owner: Vũ Đức Kiên)

**Phiên bản:** v1.0 · **Ngày:** 2026-06-11
**Mục tiêu:** Tự xây một **walking skeleton chạy thật** (không mock) ch**Ingest union amenities** (R17)o `POST /search` + `POST /context`, đủ để:

1. 2 API hoạt động đúng thiết kế trong [VuDucKien_api_schema_proposal.md](VuDucKien_api_schema_proposal.md).
2. Lấy **kết quả Evaluation thật** theo [evaluation_plan](VuDucKien_evaluation_plan%203767d4db6a3d8089b5b1f4d12630d054.md) (Recall@10, MRR, NDCG, chunk recall, citation coverage, latency p95).
3. Lấy **kết quả Monitoring thật** theo [monitoring_plan](VuDucKien_monitoring_plan%203767d4db6a3d8038816dc450bfd33262.md) (Prometheus metrics, JSON log, `/health/deep`, Grafana, per-stage latency).

---

## Phần 0 — Bối cảnh & nguyên tắc

**Thực trạng repo (2026-06-11):** Chưa có code. Chỉ có: `data/` (520 hotel JSON từ Agoda), golden set [golden_set_kien_v1.json](../evaluation/relevance_labels/golden_set_kien_v1.json) (50 query, **nhãn còn rỗng**), và các doc thiết kế. Các file mà 2 plan tham chiếu (`api/main.py`, `relational_schema.md`, `slo_defination.md`, `contracts/data_schema.json`) **chưa tồn tại**.

**Hệ quả:** Để lấy được số eval/monitoring thật, Kiên phải tự dựng **vertical slice của TẤT CẢ layer** (ingest → chunk → embed → index → retrieval → rerank → API → context → eval → monitoring), vì không layer nào của đồng đội đã thành code.

**3 nguyên tắc:**

1. **Walking skeleton trước, tối ưu sau.** Mỗi layer làm bản đơn giản nhất *chạy thật*, không mock.
2. **Seam sạch để swap-in.** Mỗi layer là 1 module có interface rõ; khi Khánh Duy/Anh Tài/Đạt/Long có bản của họ → thay 1 module, không đụng phần còn lại.
3. **Mọi số liệu tái lập được:** version index + commit hash ghi vào header report.

> **Quy mô corpus:** 520 hotel, 69 thành phố. Đủ thực tế để Recall/MRR có ý nghĩa.

---

## Phần 1 — Decision Log: phương án resolve đề xuất (chốt trước khi code)

Đây là các quyết định cần chốt. Cột "Sign-off" = ai cần xác nhận sau (Kiên build theo default này ngay, không chờ).


| #       | Mâu thuẫn                                                                                                                                        | **Phương án đề xuất (default build ngay)**                                                                                                                                                                                                                                                                                                  | Lý do                                                                      | Sign-off                  |
| ------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- | ------------------------- |
| **R1**  | `chunk_id` 3 kiểu (slug `acc_x#c2` vs `chunk-{id}-{src}-{seq}`)                                                                                  | `**chunk-{hotel_id}-{source_code}-{seq:03d}`**, `hotel_id` = **int Agoda**. Golden set đã dùng kiểu này.                                                                                                                                                                                                                                    | Citation/OpenSearch `_id`/Qdrant payload/golden labels phải khớp tuyệt đối | Khánh Duy, Long           |
| **R2**  | `hotel_id`: int vs string slug                                                                                                                   | **int Agoda ID** ở mọi nơi (805030…). KE re-key profile/objects về int.                                                                                                                                                                                                                                                                     | DB `hotels.id` + golden set đều int                                        | Long, Khánh Duy           |
| **R3**  | `source_code` set: eval §3.1 chỉ có desc/room/amen/near/act, nhưng golden set cần faq/policy/review                                              | **Mở rộng:** `desc, amen, room-{room_type_id}, near-{idx}, act-{activity_id}, faq-{idx}, policy-{idx}, review-{idx}`                                                                                                                                                                                                                        | 30/50 golden query là faq/policy/review-only                               | Kiên (cập nhật eval §3.1) |
| **R4**  | `text_chunks` Postgres table không ai build                                                                                                      | **Bỏ table này.** Chunk text = **OpenSearch `_source`** (source of truth). Qdrant chỉ giữ `{chunk_id, hotel_id, source_type}`.                                                                                                                                                                                                              | Đạt: Qdrant không lưu text dài; tránh table thừa                           | Đạt                       |
| **R5**  | Citation cần `source_table/source_column/record_id` nhưng payload KE chỉ có facet                                                                | **1 payload canonical** mang CẢ HAI (xem §3.3)                                                                                                                                                                                                                                                                                              | ContextAPI mới build được `citations[]`                                    | Khánh Duy, Long           |
| **R6**  | Method/endpoint: GET vs POST, Knowledge API                                                                                                      | **POST /search, POST /context only.** Knowledge API **out of scope**. Field names = đúng `HotelCard`/`ContextResponse`.                                                                                                                                                                                                                     | Khớp frontend + plan; giảm scope                                           | Minh Hiếu, Hiếu (FE)      |
| **R7**  | Neo4j pre-filter (Anh Tài Method A vs B)                                                                                                         | **Method A — PostgreSQL-only**, không Neo4j.                                                                                                                                                                                                                                                                                                | 2 plan đã chốt out-of-scope                                                | Anh Tài                   |
| **R8**  | `ParsedIntent.hard_filters` chỉ city/star/price                                                                                                  | **Superset:** city, star_rating, price, accommodation_type, suitable_for, amenities, review_score                                                                                                                                                                                                                                           | Golden set drive đủ 7 filter này                                           | Kiên                      |
| **R9**  | City value format                                                                                                                                | **Nạp `ontology/core/location.generated.yaml`** (79 place, `label.vi` == `hotels.city` + surface_forms bỏ dấu) → normalize city. ✅ Ontology đã có.                                                                                                                                                                                          | Không phải tự build; chuẩn hoá đúng                                        | Long ✅                    |
| **R10** | Synonym/expansion                                                                                                                                | **Nạp `ontology/synonym_dictionary.yaml`** (`surface → [concept]`) cho keyword_expansion + nhận diện amenity/object_type/city ở intent. `ontology/query_expansion.yaml` để **ablation `no_synonym`** (status `unverified` → KHÔNG bật mặc định cho số chính thức). ✅ Ontology đã có.                                                        | Không tự build; recall tốt hơn                                             | Long ✅                    |
| **R11** | Index field BM25: `embed_text` (có prefix) vs raw `text`                                                                                         | Lưu **cả hai** trong `_source`: search trên `embed_text`, trả/cite bằng `text` raw.                                                                                                                                                                                                                                                         | Citation snippet không dính prefix                                         | Khánh Duy                 |
| **R12** | Reranker variant: bge-reranker-base vs v2-m3                                                                                                     | `**BAAI/bge-reranker-v2-m3`** (đồng bộ họ bge-m3). Ghi vào eval header.                                                                                                                                                                                                                                                                     | Reproducibility                                                            | Anh Tài                   |
| **R13** | Per-stage instrumentation owner                                                                                                                  | Kiên build retrieval nên **instrument trực tiếp**: mỗi hàm trả `stage_latencies`; API wrap vào Prometheus + log.                                                                                                                                                                                                                            | Không chờ Anh Tài                                                          | Anh Tài (sau)             |
| **R14** | API schema field nguồn                                                                                                                           | `policy_notes` = `**secondary.hotel_policy.policyNotes`** (list, nested — ĐÃ verify tồn tại); `rooms.price = price_per_night`. (Đính chính: policyNotes KHÔNG mất, chỉ nằm nested.)                                                                                                                                                         | Khớp data thật                                                             | Kiên                      |
| **R15** | `top_k` vs kích thước GT                                                                                                                         | GT golden_set_v1 đã mở rộng: **min 4, max 15, mean 13** (tổng 635). → **Retrieve top_k≥15 (đề xuất 20)**, report **Recall@10 (primary, khớp eval §6.1) + Recall@15**; MRR/NDCG@10. (GS-ACT-008 chỉ 4 GT.)                                                                                                                                   | GT giờ ~13/query, không phải top-5                                         | Kiên                      |
| **R16** | `soft_signals` golden set vs concept ontology                                                                                                    | `soft_signals` là **gợi ý, KHÔNG phải concept_id ontology** (nhiều cái không tồn tại). Eval chấm **chỉ trên `relevant_hotel_ids`**. Không hard-join soft_signals.                                                                                                                                                                           | Tránh nối nhầm vocab                                                       | Kiên                      |
| **R17** | **(ĐÃ VERIFY)** Field amenity phân mảnh — chuỗi nằm rải ở `amenities_general/leisure/dining`/`amenity_groups`, không chỉ field `amenities` phẳng | **Ingest `hotels.amenities` = HỢP (union, dedupe) mọi field amenity.** Đã đo: GS-AMEN-008 "Nhà hàng" **flat 5/15 → union 15/15**; cả 10 query amenity đạt 100% (trừ non-smoking).                                                                                                                                                           | Không union → GS-AMEN-008 Recall trần 0.33 do thiết kế                     | Kiên ✅                    |
| **R18** | **(ĐÃ VERIFY)** GT mang chuỗi biến thể / thiếu tag so với hard_filter                                                                            | (a) GS-AMEN-009: 3 GT chỉ có "Phòng không hút thuốc"/"Không hút thuốc" → **filter ở mức CONCEPT `AMEN_NON_SMOKING`** (synonym_dict đã map 3 biến thể) thay vì so chuỗi literal. (b) `suitable_for` thiếu ở 3 GT (GS-FAQ-007/POL-001/POL-003) → **relabel** hoặc hạ `suitable_for` thành soft cho 3 ca này. Trần recall ~0.93 nếu không sửa. | String-exact filter giòn; concept-level bền hơn                            | Kiên + Long               |


---

## Phần 2 — Kiến trúc walking skeleton

```
                       ┌─────────────────────── FastAPI :8000 (api/) ────────────────────────┐
  golden_set ──HTTP──► │  POST /search   POST /context   GET /health[/deep]   GET /metrics   │
  run_eval.py          └───────┬───────────────┬─────────────────┬───────────────┬──────────┘
                               │               │                 │               │
                       intent_parser    context_builder    health probes   prometheus_client
                               │               │                 │
                         ┌─────▼─────┐   ┌──────▼───────┐         │
                         │ retrieval │   │ chunk select │         │
                         │  core     │   │ + citation   │         │
                         └─┬───┬───┬─┘   └──────┬───────┘         │
        SQL prefilter ─────┘   │   └── rerank   │                 │
            │            ┌─────▼─────┐ (bge)    │                 │
            ▼            │ BM25  │ Vector │      │                 ▼
      PostgreSQL :5432   │OpenSrch│ Qdrant│◄─────┘          Grafana :3000
      (hotels,rooms,     │ :9200 │ :6333 │                 Prometheus :9090
       nearby,activity)  └───────┴───────┘
            ▲                  ▲
            │ ingest_db.py     │ index.py (embed bge-m3 1024)
       data/hotel_*.json ──────┴──── chunking.py
```

**Repo structure (Kiên tạo):**

```
da10/
├── docker-compose.yml            # postgres, opensearch, qdrant, prometheus, grafana
├── requirements.txt
├── db/
│   ├── schema.sql                # DDL 4 bảng (R14 mapping)
│   └── models.py                 # SQLAlchemy (optional)
├── pipeline/
│   ├── ingest_db.py              # 520 JSON → Postgres
│   ├── chunking.py               # → chunks[] (R1/R3 chunk_id, R5 payload)
│   ├── embed.py                  # bge-m3 → 1024 vector
│   └── index.py                  # push OpenSearch + Qdrant (R4/R11)
├── core/
│   ├── intent.py                 # parse query → hard_filters + keyword_expansion (R8)
│   ├── prefilter.py              # SQL whitelist_ids (R7)
│   ├── retrieval.py              # async BM25 + vector → RRF → rerank (returns stage_latencies)
│   ├── fusion.py                 # reciprocal_rank_fusion()
│   ├── reranker.py               # bge-reranker-v2-m3 (R12)
│   └── context.py                # select chunks → context_text + citations + metadata
├── api/
│   └── main.py                   # FastAPI: /search /context /health /health/deep /metrics
├── observability/
│   ├── logging_setup.py          # JSON logger → stdout + logs/da10.jsonl
│   ├── metrics.py                # prometheus_client collectors (da10_*)
│   ├── prometheus/prometheus.yml
│   └── grafana/dashboards/da10_api.json
├── evaluation/
│   ├── run_eval.py               # golden set → API → metrics → report
│   ├── metrics_ir.py             # ranx wrappers
│   └── reports/evaluation_report.md
└── config/
    ├── city_aliases.json         # R9
    └── keyword_expansion.json    # R10 (seed từ soft_signals)
```

**Tech stack (pin):** Python 3.12 · FastAPI · `opensearch-py[async]` 2.6 · `qdrant-client` · `FlagEmbedding`/`sentence-transformers` (bge-m3, bge-reranker-v2-m3) · `asyncpg`/SQLAlchemy · `prometheus_client` · `python-json-logger` · `ranx` · `httpx` · `numpy` · OpenSearch 2.11.1 · Qdrant v1.8.0 · PostgreSQL 16 · Prometheus + Grafana.

---

## Phần 3 — Contracts đóng băng (mọi module tuân theo)

### 3.1 DDL PostgreSQL (`db/schema.sql`)

```sql
CREATE TABLE hotels (
  id BIGINT PRIMARY KEY,                 -- Agoda hotel_id (int)
  name TEXT, accommodation_type VARCHAR(100),
  star_rating NUMERIC(3,1), is_luxury BOOLEAN,
  address TEXT, city TEXT, latitude DOUBLE PRECISION, longitude DOUBLE PRECISION,
  review_score NUMERIC(3,1), review_count INT,
  description TEXT, amenities TEXT[], suitable_for TEXT[],
  useful_info JSONB, reviews_detail JSONB,
  images TEXT[], source_url TEXT
);
CREATE TABLE rooms (
  id BIGSERIAL PRIMARY KEY, hotel_id BIGINT REFERENCES hotels(id),
  room_type_id BIGINT, name TEXT, price NUMERIC(15,2),   -- = price_per_night (R14)
  room_size TEXT, max_occupancy INT, bed_type TEXT, room_view TEXT,
  room_amenities TEXT[], images TEXT[], review_score NUMERIC(3,1)
);
CREATE TABLE nearby_places (
  id BIGSERIAL PRIMARY KEY, hotel_id BIGINT REFERENCES hotels(id),
  seq INT, name TEXT, type TEXT, distance_km NUMERIC(6,2)   -- seq = index (R3, no source id)
);
CREATE TABLE activities (
  id BIGSERIAL PRIMARY KEY, hotel_id BIGINT REFERENCES hotels(id),
  activity_id BIGINT, title TEXT, description TEXT, price_amount NUMERIC(15,2), review_score NUMERIC(3,1)
);
CREATE INDEX ON hotels(city);
CREATE INDEX ON hotels USING GIN(amenities);
CREATE INDEX ON hotels USING GIN(suitable_for);
CREATE INDEX ON rooms(hotel_id);
```

### 3.2 `source_code` (R1/R3) — canonical


| source_type (API) | source_code           | Nguồn                               | record_id    |
| ----------------- | --------------------- | ----------------------------------- | ------------ |
| hotel_description | `desc`                | hotels.description                  | —            |
| amenity           | `amen`                | hotels.amenities                    | —            |
| room_info         | `room-{room_type_id}` | rooms                               | room_type_id |
| nearby            | `near-{seq}`          | nearby_places                       | seq (index)  |
| activity          | `act-{activity_id}`   | activities                          | activity_id  |
| faq               | `faq-{idx}`           | hotels.faq[]                        | idx          |
| policy            | `policy-{idx}`        | useful_info/policy faq              | idx          |
| review            | `review-{idx}`        | reviews_detail.sample_comments/tags | idx          |


Ví dụ: `chunk-805030-desc-001`, `chunk-805030-faq-003`, `chunk-805030-room-13678787-001`.

### 3.3 Chunk payload canonical (R5) — dùng cho CẢ OpenSearch `_source` lẫn Qdrant payload

```jsonc
{
  "chunk_id": "chunk-805030-desc-001",
  "hotel_id": 805030,
  "source_type": "hotel_description",      // enum API
  "source_table": "hotels",                // citation provenance
  "source_column": "description",
  "record_id": null,                       // rooms.room_type_id / nearby.seq / activity.activity_id
  "lang": "vi",
  "text": "Nằm trên hòn đảo riêng biệt...",     // RAW — để trả/cite (R11)
  "embed_text": "Vinpearl Resort Nha Trang — Mô tả. Nằm trên hòn đảo...", // có context_prefix, để BM25+vector
  "city": "Nha Trang", "accommodation_type": "Resort",  // facet filter (đồng bộ whitelist)
  "star_rating": 5.0
}
```

- **OpenSearch index** `idx_hotel_chunks_v1.0` (alias `hotel_chunks`): index `embed_text` (analyzer vi) + `text` (store) + các field filter. `_id = chunk_id`.
- **Qdrant collection** `col_documents_v1.0`: vector 1024 cosine, payload = `{chunk_id, hotel_id, source_type, city, accommodation_type, star_rating}` (nhẹ, R4). `point.id` ánh xạ `chunk_id`.

### 3.4 API contract — đóng băng theo [api_schema_proposal](VuDucKien_api_schema_proposal.md)

`POST /search` → `SearchResponse`; `POST /context` → `ContextResponse`. **Không đổi field name.** Bổ sung duy nhất: `ParsedIntent.hard_filters` mở thành superset R8.

---

## Phần 4 — Plan chi tiết theo Phase

> Mỗi phase: **Mục tiêu · File · Logic chính · Acceptance (smoke test)**. Làm tuần tự; mỗi phase phải xanh mới qua phase sau.

### Phase 0 — Môi trường & infra  *(0.5 ngày)*

- **File:** `docker-compose.yml` (copy OpenSearch/Qdrant từ [doc Đạt §7](Lê%20Hoàng%20Đạt%20(Search%20Infrastructure)%203767d4db6a3d80eeb537c28ae4143e78.md) + thêm `postgres:16`, `prometheus`, `grafana`), `requirements.txt`, `.env`.
- **Acceptance:** `docker compose up -d` → cả 5 service healthy; `curl :9200`, `:6333/healthz`, `psql` connect OK.

### Phase 1 — Ingest → PostgreSQL  *(1 ngày)*

- **File:** `db/schema.sql`, `pipeline/ingest_db.py`.
- **Logic:** Đọc 520 `data/hotel_*.json` → map field (R14: `rooms.price = price_per_night`, `nearby_places.seq = index`, `is_luxury`, `useful_info` JSONB, `reviews_detail` JSONB; policy = `secondary.hotel_policy.policyNotes`). Upsert theo `hotels.id`.
- **⚠ R17 (BẮT BUỘC):** `hotels.amenities` = **HỢP (dedupe) của `amenities` + `amenities_general` + `amenities_leisure` + `amenities_dining` + `amenity_groups.*`** — KHÔNG chỉ field `amenities` phẳng. Đã verify: nếu chỉ dùng flat, GS-AMEN-008 Recall trần 0.33; dùng union → 1.0.
- **Acceptance:** `SELECT count(*) FROM hotels` = 520; hotel 805030 có ≥1 room/nearby/activity; **kiểm:** mọi GT hotel của nhóm GS-AMEN qua được hard-filter amenity (chạy lại script đối chiếu → 10/10 query OK trừ GS-AMEN-009 xử lý theo R18).

### Phase 2 — Chunking  *(1.5 ngày)*

- **File:** `pipeline/chunking.py` → xuất `chunks.jsonl` (payload §3.3).
- **Input (accelerator):** dùng [evaluation/corpus/](../evaluation/corpus/) đã projection sẵn theo nguồn — `hotel_corpus.jsonl` (desc+amenities), `faq_activities_corpus.jsonl` (faq+activities), `policies_corpus.jsonl` (policy_notes) — 520 dòng/file. Field bị stringify → parse `ast.literal_eval`. Hoặc đọc thẳng `data/*.json` (`secondary.hotel_policy.policyNotes` cho policy — R14).
- **Logic theo loại (đồng bộ [Khánh Duy](Nguyễn%20Ngọc%20Khánh%20Duy%20(embedding%20&%20chunking)%203767d4db6a3d8016b7aae56be5556c88.md)):**
  - `desc`: recursive ~300 token (chỉ field cần băm).
  - `amen`: whole (gộp amenities thành 1–2 chunk).
  - `room-*`, `near-*`, `act-*`, `faq-*`, `review-*`, `policy-*`: **atomic**.
  - Mọi chunk: `context_prefix = "{hotel.name} — {section}. "` rồi `embed_text = prefix + text`.
  - Sinh `chunk_id` theo §3.2, gắn đủ payload §3.3.
  - **(Mới)** Tag concept rẻ vào payload qua `ontology/source_tag_map.yaml` (Tầng 0) — phục vụ filter/recall, không bắt buộc cho skeleton.
- **Acceptance:** hotel 805030 sinh được chunk `desc`, `faq`, `amen`, `room-*`, `near-*`; tổng chunk toàn corpus in ra; `chunk_id` unique.

### Phase 3 — Embedding + Indexing  *(1.5 ngày)*

- **File:** `pipeline/embed.py`, `pipeline/index.py`.
- **Logic:** bge-m3 (`FlagEmbedding`) encode `embed_text`, L2-normalize → 1024. Bulk vào OpenSearch (mapping vi analyzer, `_id=chunk_id`, store `text`+`embed_text`+filter fields) và Qdrant (`col_documents_v1.0`, cosine, payload nhẹ). Tag index version `v1.0`, alias `hotel_chunks`.
- **Acceptance:** OpenSearch `_count` = số chunk; Qdrant `collection_info.points_count` khớp; query thử BM25 "bãi biển riêng" và vector "nơi yên tĩnh gần biển" đều trả hit có `chunk_id`.

### Phase 4 — Retrieval core  *(2 ngày)*

- **File:** `core/prefilter.py`, `core/fusion.py`, `core/reranker.py`, `core/retrieval.py`.
- **Logic:**
  1. `prefilter.sql_whitelist(filters)` → `whitelist_hotel_ids` (city exact + star/price/review_score range + amenities AND `@>` + suitable_for/accommodation_type OR). Trả `[]`-aware.
  2. `retrieval.search()`: `asyncio.gather(bm25_top50, vector_top50)` cả hai lọc theo `whitelist_hotel_ids`.
  3. `fusion.reciprocal_rank_fusion(bm25, vector, k=60)` → top 15 chunk.
  4. `reranker.rerank(query, chunks)` (bge-reranker-v2-m3) → reranker_score.
  5. **Aggregate chunk→hotel:** `hotel_score = max(reranker_score)` của chunk thuộc hotel → rank hotel; lấy top_k=10. (Hotel-level metric.)
  6. Trả kèm `stage_latencies` (R13) cho từng stage.
- **Acceptance:** gọi `search("resort Nha Trang có CLB trẻ em", filters={city:"Nha Trang",accommodation_type:["Resort"]})` → trả list hotel có Vinpearl 805030; `stage_latencies` có đủ 6 key.

### Phase 5 — Intent parsing  *(1 ngày)*

- **File:** `core/intent.py` + loader cho `ontology/core/location.generated.yaml` (R9) + `ontology/synonym_dictionary.yaml` (R10).
- **Logic (rule-based default, không cần LLM):** trích city qua **location concepts** (label.vi + surface_forms bỏ dấu); star/price/review_score (số + đơn vị "sao","triệu","trên/dưới"); accommodation_type & amenity qua **synonym_dict → concept → facet** (`OBJ_*`, `AMEN_*`); suitable_for ("gia đình/cặp đôi"→`PURPOSE_*`). `keyword_expansion` = surface forms của concept khớp. `parsed_by="rule_based"`, `confidence` heuristic. (Optional LLM Ollama qwen2.5 — giữ interface.)
- **Acceptance:** parse 50 golden query → `hard_filters` khớp `golden.hard_filters` ≥ 90%.

### Phase 6 — SearchAPI  *(1 ngày)*

- **File:** `api/main.py` (`POST /search`).
- **Logic:** request → `intent.parse` → `prefilter` → `retrieval.search` → build `HotelCard[]` (join Postgres lấy name/price_from/amenities_top/nearby…) → `SearchResponse` (query_id UUID, latency_ms, parsed_intent, debug_info nếu include_debug). Xử lý `NO_RESULTS`/`ErrorResponse`.
- **Acceptance:** `curl POST /search` (ví dụ request trong api_schema) trả đúng shape `SearchResponse`; `query_id` là UUID; `total_found`/`returned` đúng; zero-result query (GK-031 Tokyo) trả `results:[]` không lỗi.

### Phase 7 — Context construction + ContextAPI  *(1.5 ngày)*

- **File:** `core/context.py`, `api/main.py` (`POST /context`).
- **Logic:** nhận `hotel_id`+`query` → lấy chunk của hotel đó từ OpenSearch → rerank theo query → chọn top-K tới `max_context_tokens` → `context_text` = concat (không LLM synthesis) → build `citations[]` (từ payload `source_table/source_column/record_id` — R5) → `metadata` (join Postgres: rooms[], nearby_places[], activities[], useful_info…) → `token_info` (tiktoken `cl100k_base`) nếu bật.
- **Acceptance:** `POST /context {hotel_id:805030, query:"hòn đảo riêng yên tĩnh"}` → `chunks[]` non-empty, mỗi citation có `chunk_id` trỏ chunk thật, `context_text` chứa text raw (không prefix), `metadata.rooms` đầy.

### Phase 8 — Observability  *(1.5 ngày)*

- **File:** `observability/metrics.py`, `logging_setup.py`, `prometheus/prometheus.yml`, `grafana/dashboards/da10_api.json`; wire vào `api/main.py`.
- **Logic (theo monitoring_plan §6–9):**
  - Metrics: `da10_http_requests_total{endpoint,method,status}`, `da10_http_request_duration_seconds{endpoint}` (buckets §6.3), `da10_search_zero_results_total{search_mode}`, `da10_context_build_duration_seconds`, `da10_stage_duration_seconds{stage}` (từ `stage_latencies` R13), `da10_dependency_up{dependency}`.
  - JSON log middleware: schema §7.2/7.3, `request_id` xuyên search→context, ghi `logs/da10.jsonl`.
  - `GET /health` shallow; `GET /health/deep` ping OpenSearch+Qdrant+Postgres → 503 nếu fail, cập nhật gauge.
  - Grafana dashboard panels §9.2 (Search/Context p95, request/error/zero-result rate, stage breakdown, dependency up).
- **Acceptance:** `GET /metrics` ra các `da10_*`; `/health/deep` = all ok; sau vài request, Grafana panel p95 có số; `logs/da10.jsonl` có dòng `search_completed` với `stages_ms`.

### Phase 9 — Evaluation harness  *(2 ngày)*

- **File:** `evaluation/run_eval.py`, `metrics_ir.py`.
- **Golden set:** `golden_dataset/golden_set_v1.json` (49 query, 5 nhóm DESC/FAQ/ACT/POL/AMEN; `relevant_hotel_ids` **đã điền**).
- **Logic (theo evaluation_plan §6, §9):**
  - Đọc golden set; mỗi query: `POST /search {top_k:10}` → tính **@5 VÀ @10** (Recall, MRR, NDCG, Hit), Zero-result (binary vs `relevant_hotel_ids`, xử lý `|GT|<5` — R15). **Primary = @5.** Rồi `POST /context {hotel_id:results[0]}` → Chunk Recall@K, Citation Coverage vs `relevant_chunk_ids` (khi đã gán chunk).
  - **Breakdown theo 5 nhóm** (DESC/FAQ/ACT/POL/AMEN) — soi pipeline mạnh/yếu ở nguồn bằng chứng nào.
  - **Latency protocol §9.1:** warmup 10 query, 50×3 lần, p95 (numpy) cho `/search` và `/context`.
  - Header reproducibility §5 (commit, dataset_version, index version, embedding_model, search_mode, top_k). Output Markdown theo template §12.
  - `--mode bm25_only|vector_only|hybrid_no_rerank|full_hybrid` để chạy baseline/ablation §7.
  - `--smoke` dùng `smoke_queries_kien.json` (5 query) cho PR.
- **Acceptance:** `python run_eval.py --mode full_hybrid` sinh `evaluation_report.md` có đủ bảng số; chạy thêm `--mode bm25_only` để có cột so sánh §7.3.

### Phase 10 — Full run + reports  *(1 ngày)*

- Gán nhãn golden set (xem Phần 6) → chạy full eval cả `full_hybrid` + `bm25_only` → điền `evaluation_report.md`. Snapshot Grafana → `monitoring_report.md` (template §11.2). Cross-check client p95 (eval) vs server p95 (Prometheus).
- **Acceptance:** 2 report có số thật; SLO check (<500ms) + regression (full_hybrid ≥ bm25_only) ghi rõ pass/fail.

---

## Phần 5 — Ánh xạ deliverable → 2 plan


| Plan yêu cầu                                     | Sinh ra ở                           | Cách lấy số                                                  |
| ------------------------------------------------ | ----------------------------------- | ------------------------------------------------------------ |
| Recall@10/MRR@10/NDCG@10/Hit@5 (eval §6.1)       | Phase 9                             | ranx trên `relevant_hotel_ids`                               |
| Chunk Recall@K, Citation Coverage (eval §6.2)    | Phase 9                             | so `chunks[].chunk_id`/`citations[]` vs `relevant_chunk_ids` |
| Latency p95 /search /context (eval §6.3, mon §4) | Phase 9 (client) + Phase 8 (server) | httpx 50×3 + Prometheus histogram                            |
| Zero-result <5% (mon §4)                         | Phase 8/9                           | `da10_search_zero_results_total` / counter                   |
| Baseline bm25_only + ablation (eval §7)          | Phase 9                             | `--mode` flag                                                |
| Prometheus + Grafana + per-stage (mon §6,9)      | Phase 8                             | `da10_*`, dashboard JSON                                     |
| JSON log + request_id (mon §7)                   | Phase 8                             | `logs/da10.jsonl`                                            |
| `/health/deep` all-up (mon §8)                   | Phase 8                             | endpoint                                                     |
| Human rubric Context Quality (eval §6.4)         | thủ công sau Phase 7                | `rubric_scores_v1.xlsx`, ≥10 query                           |


---

## Phần 6 — Gán nhãn golden set (cập nhật theo golden_set_v1)

Dùng `**golden_dataset/golden_set_v1.json`** (49 query) làm canonical, KHÔNG dùng `golden_set_kien_v1.json` cũ.

1. **Hotel labels — ĐÃ XONG ✅:** `relevant_hotel_ids` đã điền đầy đủ (int Agoda, đã verify tồn tại trong `data/`, sorted theo relevance). → Hotel-level eval chạy được ngay khi Search hoạt động (Phase 6). Không cần gán thêm.
2. **Chunk labels — còn lại:** `relevant_chunk_ids=[]`. Sau Phase 3 (index v1 có chunk), điền `chunk_id` thật (vd `chunk-805030-faq-003`) theo nhóm: DESC→`desc`, FAQ→`faq`, ACT→`act`, POL→`policy`, AMEN→`amen`. Đây là việc duy nhất còn chặn **chunk metrics**.
3. **Lưu ý GT là top-5 sorted** (R15) + `soft_signals` chỉ là gợi ý (R16) — chấm trên `relevant_hotel_ids`.

---

## Phần 7 — Lịch trình & swap-in

**Tổng ~17 ngày công** (1 người), bám sprint trong 2 plan:


| Tuần  | Phase | Mốc                                                     |
| ----- | ----- | ------------------------------------------------------- |
| S2-T1 | 0,1,2 | infra + DB + chunking; gán hotel labels                 |
| S2-T1 | 3,4   | index v1 + retrieval chạy; gán chunk labels             |
| S2-T2 | 5,6,7 | 2 API chạy end-to-end (smoke 5 query)                   |
| S2-T2 | 8,9   | monitoring + run_eval v0 → `evaluation_report.md` draft |
| S3    | 10    | full eval + baseline + Grafana → 2 report final + demo  |


**Seam swap-in (khi đồng đội xong):**

- Khánh Duy/Long có `knowledge_objects.json` thật → thay `pipeline/chunking.py` (giữ payload §3.3).
- Đạt có `search_service.py`/`vector_search.py` → thay client trong `core/retrieval.py`.
- Anh Tài có `SearchEngine` → thay `core/retrieval.py` (giữ chữ ký + `stage_latencies`).
- Long có `synonym_dictionary.yaml` → thay `config/keyword_expansion.json` + `city_aliases.json`.

Mọi swap **không đổi API contract §3.4** → eval/monitoring tái chạy không sửa.

---

## Phần 8 — Rủi ro


| Rủi ro                                   | Giảm thiểu                                                                                           |
| ---------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| bge-m3 + reranker chậm trên CPU (p95)    | Batch embed offline (Phase 3); reranker chỉ top-15; cache; nếu cần, đo p95 với top_k giảm và ghi chú |
| Chunk labels chưa kịp                    | Chạy hotel metrics trước (đủ Recall/MRR/NDCG); chunk metrics "báo cáo" như plan cho phép             |
| Postgres city không khớp query không dấu | `city_aliases.json` + normalize fold dấu (R9)                                                        |
| Đồng đội đổi schema giữa chừng           | Contract §3 versioned; chỉ swap module sau seam                                                      |


---

*Hết. Build theo Phase 0→10; mỗi phase xanh acceptance mới đi tiếp. Kết quả cuối: 2 API đúng thiết kế + `evaluation_report.md` + `monitoring_report.md` có số thật, tái lập được.*