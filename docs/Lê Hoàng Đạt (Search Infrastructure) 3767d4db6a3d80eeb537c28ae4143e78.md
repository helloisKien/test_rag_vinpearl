# Lê Hoàng Đạt (Search Infrastructure)

![search infra e2e.png](search_infra_e2e.png)

# SEARCH ARCHITECTURE SPECIFICATION

**Phân hệ:** Search Infrastructure | **Hệ thống:** DA10- OTA AI Search Platform
**Owner:** Lê Hoàng Đạt | **Backup:** Nguyễn Anh Tài | **Trạng thái:** Bản đầy đủ

> **Quyết định team:** BM25 lexical engine = **OpenSearch 2.x** (`opensearchproject/opensearch:2.11.1`).
> Client: `opensearch-py>=2.6.0,<3.0.0` (`AsyncOpenSearch`). Elasticsearch không còn dùng trong DA10.

---

## 1. Tổng Quan Hệ Thống & Phạm Vi (System Overview & Scope)

Hệ thống hạ tầng tìm kiếm của DA10 đóng vai trò là “trọng tâm xử lý dữ liệu”, chịu trách nhiệm lưu trữ văn bản thô, siêu dữ liệu (metadata), và các vector đặc trưng (embeddings) thu được từ luồng xử lý trước đó. Mục tiêu tối thượng của phân hệ này là cung cấp khả năng tìm kiếm lai (**Hybrid Search**) kết hợp giữa:

1. **Từ khóa truyền thống (Lexical/Keyword Search - BM25):** Đảm bảo độ chính xác tuyệt đối với các thực thể, mã phòng, địa danh cố định.
2. **Ngữ nghĩa sâu (Semantic/Vector Search):** Đảm bảo hiểu được ý định tìm kiếm của người dùng ngay cả khi không trùng khớp từ khóa gốc.

Hạ tầng này cam kết đáp ứng nghiêm ngặt các chỉ số SLO về hiệu năng tải và khả năng tái lập (reproducibility) theo yêu cầu từ Mentor.

---

## 2. Kiến Trúc Luồng Dữ Liệu Toàn Diện (End-to-End Data Flow)

Hệ thống được chia tách nghiêm ngặt thành 2 luồng độc lập để tối ưu hóa hiệu năng ghi tải và tốc độ đọc.

### 2.1. Luồng Ghi Dữ Liệu (Write Path - Ingestion Pipeline)

Luồng này chạy bất đồng bộ (Async) hoặc theo mẻ (Batch) khi hệ thống cập nhật tri thức mới.

```
[Dữ liệu Thô]
     │
     ▼
[Data Quality (Đỗ Minh Hiếu)] ────> Thực thi validation_rules.md & clean dữ liệu
     │
     ▼ (mock_documents_v1.json)
[Chunk & Embed (Nguyễn Ngọc Khánh Duy)] ──> Cắt nhỏ văn bản + Hóa vector qua Embedding Service
     │
     ▼ (Đồng thời cả Text + Vector + Metadata)
[Search Infrastructure (Lê Hoàng Đạt)]
     ├── Đẩy Full Text & Metadata ──────> [OpenSearch Cluster] ──> Index: idx_hotel_chunks_v1.0 (alias: hotel_chunks)
     └── Đẩy Vector IDs & Payload ──────> [Qdrant Cluster]      ──> Collection: col_documents_v1.0
```

### 2.2. Luồng Đọc Dữ Liệu (Read Path - Retrieval Pipeline)

Luồng này chạy theo thời gian thực (Real-time), yêu cầu tối ưu hóa tối đa để đạt p95 Latency < 500ms tổng thể.

```
[User Query] ────> [API Server (Vũ Đức Kiên)] ────> [Retrieval Core (Nguyễn Anh Tài)]
                                                               │
                                         ┌─────────────────────┴─────────────────────┐
                                         ▼ (Async Parallel Query)                    ▼ (Async Parallel Query)
                            [OpenSearch: BM25]                            [Qdrant: Vector Search]
                            - Khớp từ khóa chính xác                     - Tìm kiếm ngữ nghĩa gần nhất
                            - Trả về Top 50 Candidates                   - Trả về Top 50 Candidates
                                         │                                           │
                                         └─────────────────────┬─────────────────────┘
                                                               ▼
                                                  [RRF Fusion & Re-ranking]
                                                  - Trộn kết quả bằng Reciprocal Rank Fusion
                                                  - Tái xếp hạng (Reranker Module)
                                                               │
                                                               ▼
                                                  [Top-K Context + Citations Ready] ───> Bàn giao cho DA09
```

---

## 3. Thiết Kế Thành Phần Lưu Trữ Chi Tiết (Storage Component Design)

### 3.1. Phân Hệ OpenSearch (Keyword Engine)

- **Thuật toán cốt lõi:** BM25 ($k_1 = 1.2$, $b = 0.75$) — mặc định OpenSearch 2.x.
- **Cấu hình Ngôn ngữ (OpenSearch 2.x):**
  - **Ingest:** tokenize/chuẩn hóa tiếng Việt bằng `underthesea` (đồng bộ với Ontology / Data Quality) trước khi index.
  - **Index analyzer:** `standard` + `asciifolding` + `lowercase` (built-in, không cần plugin ES).
- **Index:** vật lý `idx_hotel_chunks_v1.0`, alias truy vấn `hotel_chunks`.
- **Index Mapping Schema (`index_mapping.json`):**

```json
{
  "settings": {
    "index": {
      "analysis": {
        "analyzer": {
          "vi_default": {
            "type": "custom",
            "tokenizer": "standard",
            "filter": ["lowercase", "asciifolding"]
          }
        }
      }
    }
  },
  "mappings": {
    "properties": {
      "id": { "type": "keyword" },
      "embed_text": { "type": "text", "analyzer": "vi_default", "boost": 2.0 },
      "content": { "type": "text", "analyzer": "vi_default" },
      "metadata": {
        "properties": {
          "location": { "type": "keyword" },
          "category": { "type": "keyword" },
          "created_at": { "type": "date" }
        }
      }
    }
  }
}
```

### 3.2. Phân Hệ Qdrant (Vector Engine)

- **Metric khoảng cách:** Cosine Similarity.
- **Cấu hình Không gian Vector (Vector Space):** Khởi tạo dựa trên mô hình Embedding được chọn (Mặc định cấu hình sẵn cho `bge-m3`).
- **Thông số kỹ thuật Collection:**
    - `vectors.size`: 1024 (Độ dài vector đầu ra của mô hình).
    - `vectors.distance`: `Cosine`.
    - `hnsw_config.m`: 16 (Số lượng liên kết tối đa của mỗi node trong đồ thị HNSW để tăng tốc tìm kiếm).

---

## 4. Chiến Lược Quản Lý Schema & Đánh Version (Reproducibility & Protocols)

Để giải quyết triệt để yêu cầu về việc **“Demo có khả năng tái lập độc lập”** và **“Quy trình thay đổi schema giữa chừng”** từ Mentor, hạ tầng áp dụng hai giao thức sau:

### 4.1. Quy tắc đặt tên và Đóng băng Index (Versioning Index)

- Tất cả dữ liệu ghi vào DB không được phép ghi đè lên các bản phân phối cũ.
- Tên định danh tuân thủ cấu trúc nghiêm ngặt: `[loại_db]_[tên_hợp_đồng]_[phiên_bản]`.
    - *Ví dụ OpenSearch:* `idx_hotel_chunks_v1.0`, `idx_hotel_chunks_v1.1` (alias: `hotel_chunks`).
    - *Ví dụ Qdrant:* `col_documents_v1.0`, `col_documents_v1.1`.
- Khi chạy demo cuối kỳ, mã nguồn của hệ thống sẽ gọi chính xác số hiệu phiên bản đã được gán nhãn thành công với bộ dữ liệu Golden Dataset mẫu.

### 4.2. Giao thức Thay Đổi Schema (Schema Change Protocol)

Khi `data_schema.json` từ nhóm DA09 hoặc Đỗ Minh Hiếu thay đổi giữa chừng:
1. **Trạng thái cô lập:** Đạt lập tức khóa luồng ingest hiện tại, tạo một GitHub Issue thông báo toàn nhóm.
2. **Nâng cấp phiên bản:** Tạo một file `index_mapping_vNext.json` mới mà không xóa file cũ.
3. **Tái cấu trúc (Re-index):** Chạy script nội bộ để chuyển đổi và đẩy lại dữ liệu từ phiên bản cũ sang phiên bản mới, đổi tên alias trỏ tới index mới sau khi đã thống nhất với phân hệ API của Vũ Đức Kiên.

---

## 5. Ranh Giới Tích Hợp & Giao Tiếp Giữa Các Thành Viên (Interface Boundaries)

Để hạ tầng vận hành mượt mà, các điểm chạm thông tin đầu vào (Input) và đầu ra (Output) được quy định rõ:

```

┌──────────────────────────────────────────────────────────────────────────────────┐
│                             MA TRẬN GIAO TIẾP (INTERFACE)                        │
├───────────────────────┬──────────────────────────────────────────────────────────┤
│ Nhận từ Đỗ Minh Hiếu  │ File `data_schema.json` để viết cấu trúc ánh xạ cấu trúc  │
│                       │ dữ liệu gốc vào trường dữ liệu OpenSearch.               │
├───────────────────────┼──────────────────────────────────────────────────────────┤
│ Nhận từ Khánh Duy     │ Số chiều Vector (Dimension) và mẻ dữ liệu embeddings thô │
│                       │ để khởi tạo cấu hình Collection trên Qdrant.             │
├───────────────────────┼──────────────────────────────────────────────────────────┤
│ Bàn giao cho Anh Tài  │ - SDK kết nối/Cấu hình Port vào 2 Cụm Cơ sở dữ liệu.     │
│                       │ - File module nền tảng `search_service.py` (BM25 via     │
│                       │   OpenSearch) và `vector_search.py` để Tài gọi truy vấn.  │
├───────────────────────┼──────────────────────────────────────────────────────────┤
│ Bàn giao cho Đức Kiên │ Các số liệu đo đạc Latency thuần tại tầng DB để phục vụ   │
│                       │ việc tính toán chỉ số p95 End-to-End của toàn hệ thống.  │
└───────────────────────┴──────────────────────────────────────────────────────────┘
```

## 6. Chiến Lược Tối Ưu Tải & Đạt SLO Latency (p95 < 500ms)

1. **Chiến lược Lọc Trước (Pre-filtering):**
Cấu hình Qdrant thực hiện lọc các trường Metadata (như vị trí, danh mục) *ngay trong quá trình* duyệt đồ thị HNSW của Vector Search. Tuyệt đối không dùng Post-filtering (tìm kiếm vector xong mới lọc thuộc tính) nhằm tránh hiện tượng thắt nút cổ chai hiệu năng và suy giảm độ chính xác.
2. **Truy vấn Song song Thực sự (Parallel Vector-Lexical Execution):**
Phối hợp cùng Anh Tài thiết kế hàm gọi DB sử dụng mô hình Asynchronous I/O (`asyncio` trong Python). Khi nhận query, luồng đọc sẽ bắn đồng thời 1 request sang OpenSearch và 1 request sang Qdrant, thời gian trễ của tầng lưu trữ sẽ chỉ bằng $\max(\text{Latency}_{\text{OS}}, \text{Latency}_{\text{Qdrant}})$ thay vì tổng cộng dồn của hai bên.
3. **Tối ưu Hóa Tài Nguyên Index (Payload Tuning):**
Không lưu trữ toàn bộ các đoạn văn bản quá dài hoặc dữ liệu nhị phân không cần thiết bên trong payload của Qdrant. Chỉ lưu giữ ID văn bản và các thẻ metadata phục vụ bộ lọc để dung lượng RAM của Qdrant được giải phóng tối đa, ưu tiên cho việc cache đồ thị tìm kiếm.

## 7. Bản Thiết Kế Hạ Tầng Kiểm Thử Hoàn Chỉnh (`docker-compose.yml`)

```yaml
version: '3.8'

services:
  opensearch:
    image: opensearchproject/opensearch:2.11.1
    container_name: da10_search_opensearch
    environment:
      - discovery.type=single-node
      - plugins.security.disabled=true
      - DISABLE_INSTALL_DEMO_CONFIG=true
      - "OPENSEARCH_JAVA_OPTS=-Xms1g -Xmx1g"
    ports:
      - "9200:9200"
      - "9600:9600"
    volumes:
      - opensearch_storage_data:/usr/share/opensearch/data
    healthcheck:
      test: ["CMD-SHELL", "curl -s http://localhost:9200/_cluster/health | grep -q 'status.*\\(green\\|yellow\\)'"]
      interval: 10s
      timeout: 5s
      retries: 3

  qdrant:
    image: qdrant/qdrant:v1.8.0
    container_name: da10_vector_qdrant
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_storage_data:/qdrant/storage
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6333/healthz"]
      interval: 10s
      timeout: 5s
      retries: 3

volumes:
  opensearch_storage_data:
    driver: local
  qdrant_storage_data:
    driver: local
```

## 8. Quản Trị Rủi Ro & Cơ Chế Giảm Thiểu Bus Factor

- **Đạt ──> Anh Tài:** Cung cấp địa chỉ IP/Port của Service, tên Index/Collection hiện tại (`v1/v2`), và cấu trúc kết quả trả về của OpenSearch/Qdrant để Tài viết hàm Fusion.
- **Khánh Duy ──> Đạt:** Cung cấp thông số cấu hình Vector (Số chiều: 384, 768 hay 1024) để Đạt tạo cấu trúc Collection trên Qdrant.
- **Đạt ↔︎ Anh Tài (Pair/Backup):** Đạt có trách nhiệm giải thích cho Tài cách chạy docker-compose và cấu trúc file `index_mapping.json`. Khi Đạt vắng mặt, Tài phải có khả năng start/stop cluster và kiểm tra log của DB để tìm lỗi.