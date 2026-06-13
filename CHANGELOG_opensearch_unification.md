# Changelog: Thống nhất BM25 Engine → OpenSearch 2.x

**Ngày cập nhật:** 2025-06-07  
**Phạm vi:** Đồng bộ tài liệu kiến trúc DA10 sau khi team chốt dùng **OpenSearch 2.x** cho toàn bộ pipeline BM25 lexical search.

---

## 1. Bối cảnh & lý do thay đổi

### Vấn đề trước khi sửa

Các doc trong `docs/` mâu thuẫn về engine BM25 lexical:

| Thành viên / doc | Engine cũ trong doc |
|------------------|---------------------|
| Lê Hoàng Đạt (Search Infra) | Elasticsearch 8.12.0 |
| Nguyễn Anh Tài (Retrieval) | Elasticsearch 8.11.1, `elasticsearch[async]`, `index_elasticsearch.py` |
| Đỗ Minh Hiếu (Data Quality) | OpenSearch 2 (đã đúng hướng) |
| Nguyễn Ngọc Khánh Duy (Chunking) | OpenSearch (đã đúng hướng) |
| Trương Anh Long (Ontology) | Elasticsearch (trong RACI / tech stack) |
| Vũ Đức Kiên (API schema) | Comment ghi Elasticsearch |

Hệ quả: nếu Search Infra setup Elasticsearch nhưng Chunking index vào OpenSearch, retrieval pipeline không biết kết nối vào hệ thống nào — **blocker thực sự** trước khi SearchAPI chạy end-to-end.

### Quyết định team

- **BM25 lexical engine duy nhất:** OpenSearch 2.x
- **Không dùng Elasticsearch** trong DA10

### Mục tiêu đợt sửa doc

1. Một **single source of truth** cho hạ tầng BM25 (doc Search Infra).
2. Đồng bộ version, client, index naming, analyzer across toàn bộ docs.
3. Giữ tên field API `bm25_*` (mô tả thuật toán, không phải tên product).

---

## 2. Thông số kỹ thuật đã chốt (canonical)

| Hạng mục | Giá trị | Lý do |
|----------|---------|-------|
| Docker image | `opensearchproject/opensearch:2.11.1` | Pin version ổn định; gần với ES 8.11.1 từng dùng trong POC của Anh Tài |
| Port | `9200` (REST), `9600` (perf analyzer) | Giữ port chuẩn, khớp doc Data Quality |
| Python client | `opensearch-py>=2.6.0,<3.0.0` | Package chính thức cho OpenSearch; hỗ trợ `AsyncOpenSearch` cho parallel retrieval |
| Vietnamese text | `underthesea` (ingest) + analyzer built-in `standard/asciifolding/lowercase` (index) | Plugin `elasticsearch-analysis-vietnamese` không dùng được trên OpenSearch; `underthesea` đã có trong stack Ontology/Data Quality |
| Index vật lý | `idx_hotel_chunks_v1.0` | Versioning rõ ràng, tái lập được |
| Index alias (query) | `hotel_chunks` | Khớp pipeline Retrieval; truy vấn qua alias, re-index không đổi code |
| Field BM25 chính | `embed_text` | Contextual BM25 (có `context_prefix` từ Khánh Duy) |
| Index script | `scripts/run_index.py` (orchestrator), optional `index_opensearch.py` | Khớp layout Data Quality; thay `index_elasticsearch.py` |
| Module BM25 | `search_service.py` (giữ tên) | Tên generic; implementation dùng OpenSearch client |
| Vector DB | `qdrant/qdrant:v1.8.0` | Không đổi — đã thống nhất trước đó |

---

## 3. Chi tiết thay đổi theo từng file

### 3.1 `Lê Hoàng Đạt (Search Infrastructure)...md` — **Owner doc (sửa nhiều nhất)**

**Vai trò sau sửa:** Single source of truth cho OpenSearch + Qdrant infra.

| Section | Thay đổi | Lý do |
|---------|----------|-------|
| Header | Thêm block **Quyết định team** (OpenSearch 2.11.1, `opensearch-py`, không dùng ES) | Ghi nhận quyết định chính thức, tránh tranh cãi lại |
| §2.1 Write path | `Elasticsearch Cluster` → `OpenSearch Cluster`; index `idx_documents_v1.0` → `idx_hotel_chunks_v1.0` (alias `hotel_chunks`) | Đồng bộ engine + thống nhất tên index với Retrieval |
| §2.2 Read path | `Elasticsearch: BM25` → `OpenSearch: BM25` | Pipeline hybrid trỏ đúng engine |
| §3.1 | Đổi title → **Phân Hệ OpenSearch**; bỏ `elasticsearch-analysis-vietnamese`; thêm chiến lược `underthesea` + built-in analyzer; cập nhật `index_mapping.json` (field `embed_text`, analyzer `vi_default`) | Plugin ES-only không portable; mapping khớp chunking contextual |
| §4.1 Versioning | Ví dụ index → `idx_hotel_chunks_v1.0/v1.1` + alias | Versioning nhất quán |
| §5 Interface matrix | Elasticsearch → OpenSearch; `search_service.py` ghi rõ "BM25 via OpenSearch" | Ranh giới tích hợp rõ cho Anh Tài |
| §6 Latency | `Latency_ES` → `Latency_OS`; request sang OpenSearch | Thuật ngữ khớp stack mới |
| §7 docker-compose | Thay toàn block ES 8.12.0 bằng OpenSearch 2.11.1; sửa env (`plugins.security.disabled`, `OPENSEARCH_JAVA_OPTS`); volume `opensearch_storage_data`; fix YAML indent | Compose chạy được; một image duy nhất cho cả team |
| §8 Bus factor | `ES/Qdrant` → `OpenSearch/Qdrant` | Handoff doc cho backup owner |

**Doc không sửa:** §3.2 Qdrant (giữ nguyên).

---

### 3.2 `Nguyễn Anh Tài (Retrieval & Ranking)...md`

| Section | Thay đổi | Lý do |
|---------|----------|-------|
| Stage 3 pipeline | `Elasticsearch BM25` → `OpenSearch BM25`; query qua alias `hotel_chunks` | Retrieval kết nối đúng engine + index team chốt |
| Stage 4 | `BM25 (Elasticsearch)` → `BM25 (OpenSearch)`; bỏ mention `pgvector` ở fusion | Chỉ dùng Qdrant cho vector trong stack chốt |
| Phương pháp A | Title + hạ tầng: `ES`/`Elasticsearch` → `OpenSearch 2.x + Qdrant` | Baseline A phản ánh kiến trúc thực |
| Phương pháp B | Tương tự; `ES BM25` → `OpenSearch BM25` | Baseline B đồng bộ |
| Task 1.2 | Docker: `Elasticsearch 8.11.1` → `OpenSearch 2.11.1`; `index_elasticsearch.py` → `scripts/run_index.py` / `index_opensearch.py`; thêm dòng kết nối `:9200`, alias `hotel_chunks` | POC setup khớp infra mới |
| Task 2.3 | `elasticsearch[async]` → `opensearch-py` (`AsyncOpenSearch`) | Client đúng product |
| Task 2.4 | Nguồn kết quả RRF: OpenSearch thay Elasticsearch | Fusion input nhất quán |

---

### 3.3 `Đỗ Minh Hiếu (data quality)...md` — **Đã đúng hướng, tinh chỉnh**

| Section | Thay đổi | Lý do |
|---------|----------|-------|
| Sơ đồ L6 | `OpenSearch 2` → hiển thị `v2.11.1 · port 9200` | Pin version cụ thể |
| Bảng L4 / Storage | `OpenSearch 2` → `OpenSearch 2.11.1` | Đồng bộ với doc Search Infra |
| Deployment Architecture | Thêm image tag + footnote tham chiếu doc Đạt §7 | Tránh duplicate compose không khớp |
| Design Decisions | Cập nhật dòng OpenSearch: lý do team chốt + `opensearch-py` | Ghi rõ rationale |

**Doc không sửa:** Logic pipeline Layer 2, cleaning, validation (không liên quan BM25 engine).

---

### 3.4 `Nguyễn Ngọc Khánh Duy (embedding & chunking)...md` — **Bổ sung contract**

| Section | Thay đổi | Lý do |
|---------|----------|-------|
| §6 (sau BA ENGINE) | Thêm block **Contract indexing (Layer 4 → Search Infra)** | Khánh Duy biết chính xác đẩy chunk vào đâu: OpenSearch 2.11.1, alias, field `embed_text` |
| Diagram mermaid | Giữ `BM25 index (OpenSearch)` | Đã đúng từ trước |

---

### 3.5 `Trương Anh Long (Ontology)...md` — **2 chỗ**

| Section | Thay đổi | Lý do |
|---------|----------|-------|
| RACI (~dòng 106) | `Elasticsearch + Qdrant` → `OpenSearch + Qdrant` | Phân công owner Search Infra khớp stack |
| Tech stack (~dòng 228) | `Qdrant + Elasticsearch` → `Qdrant + OpenSearch 2.x` | Bảng công nghệ nhất quán |

**Doc không sửa:** Các mention **BM25** / hybrid BM25+vector (mô tả thuật toán, vẫn đúng).

---

### 3.6 `VuDucKien_api_schema_proposal.md` — **Chỉ comment**

| Field | Thay đổi | Lý do |
|-------|----------|-------|
| `bm25_candidates` comment | Elasticsearch → OpenSearch (BM25) | Comment phản ánh backend thực |
| `bm25_rank` comment | Elasticsearch → OpenSearch BM25 | Tương tự |

**Không đổi:** Tên field `bm25_candidates`, `bm25_rank` — vẫn mô tả thuật toán/xếp hạng lexical, không phụ thuộc tên vendor.

---

### 3.7 `NguyenDuyHieu_FRONTEND_ARCHITECTURE...md`

**Không sửa** — Frontend không kết nối trực tiếp OpenSearch/Elasticsearch.

---

## 4. Những gì cố ý KHÔNG thay đổi

| Mục | Lý do |
|-----|-------|
| Tên field API `bm25_*` | BM25 là tên thuật toán; đổi thành `opensearch_*` sẽ breaking change API không cần thiết |
| Qdrant version `v1.8.0` | Đã thống nhất, không nằm trong scope mâu thuẫn ES/OS |
| Logic Neo4j trong doc Anh Tài | Vẫn là phương án thử nghiệm A/B; chỉ đổi phần lexical engine |
| Frontend architecture | Out of scope |

---

## 5. Checklist verify sau khi sửa

- [x] Grep `docs/` không còn `Elasticsearch`, `elasticsearch`, `docker.elastic`, `ES_JAVA_OPTS`, `index_elasticsearch`, `elasticsearch[async]`
- [x] Chỉ còn 1 mention Elasticsearch: ghi rõ *"Elasticsearch không còn dùng trong DA10"* (doc Search Infra)
- [x] Mọi doc BM25 lexical đều trỏ OpenSearch 2.11.1
- [x] Index naming thống nhất: physical `idx_hotel_chunks_v1.0`, alias `hotel_chunks`
- [x] Client thống nhất: `opensearch-py`

---

## 6. Việc còn lại (ngoài scope sửa doc)

Các hạng mục sau **chưa có trong repo** — team cần implement riêng:

1. **`docker-compose.yml` thật** ở root repo (hiện chỉ mô tả trong doc Đạt §7).
2. **Migrate code POC** nếu Anh Tài/Đạt đã viết với `elasticsearch-py` hoặc chạy ES container thật.
3. **`requirements.txt`** pin `opensearch-py>=2.6.0,<3.0.0`.
4. **Script indexing** `scripts/run_index.py` / `index_opensearch.py` triển khai theo contract mới.

---

## 7. Tham chiếu nhanh

| Cần biết | Xem doc |
|----------|---------|
| Docker compose + index mapping | Lê Hoàng Đạt (Search Infrastructure) §3, §7 |
| Retrieval pipeline + async client | Nguyễn Anh Tài (Retrieval & Ranking) §1, Task 2.3 |
| Indexing contract từ chunking | Nguyễn Ngọc Khánh Duy §6 |
| Layer pipeline tổng thể | Đỗ Minh Hiếu (data quality) |
| API field semantics | VuDucKien_api_schema_proposal.md |
