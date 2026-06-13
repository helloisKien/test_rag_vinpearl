# Nguyễn Anh Tài (Retrieval & Ranking)

## Nguyễn Anh Tài - Retrieval & Ranking

# Bản Thiết Kế Kiến Trúc & Lộ Trình R&R (Retrieval & Ranking) Hiệu Chỉnh

Tài liệu này định nghĩa kiến trúc, các phương pháp thử nghiệm và lộ trình thực thi chi tiết cho vị trí **Retrieval & Ranking (R&R) Owner** trong dự án AI Travel Assistant (DA10). Lộ trình này được thiết kế để thử nghiệm và chốt kiến trúc tối ưu (Có hay không dùng Neo4j Graph) ngay từ đầu Sprint 2, giúp định hướng lập trình tối ưu hóa các tính năng mà không bị lãng phí tài nguyên phát triển song song.

---

## 1. KIẾN TRÚC LÕI PIPELINE R&R (HYBRID DESIGN)

Hệ thống RAG sử dụng cơ chế tìm kiếm lai (Hybrid Search) kết hợp lọc cứng (Relational), từ khóa (Lexical) và tìm kiếm ngữ nghĩa (Semantic) qua 5 giai đoạn chạy theo dạng phễu để tối ưu độ chính xác và giảm độ trễ.

```
[User Query]
   │
   ▼
Stage 1: Intent Parsing (Ollama local qwen2.5:7b + Rule-based Fallback) [Thử nghiệm]
   ├─> Hard Filters: Thành phố, Hạng sao, Giá trần
   ├─> Graph Concepts: Khớp mờ ontology tags/amenities (STYLE_QUIET, AMEN_PRIVATE_POOL...)
   └─> Keyword Expansion: Chuỗi từ khóa mở rộng cho BM25
   │
   ▼
Stage 2: Relational & Graph Pre-filtering (PostgreSQL SQL + Neo4j Cypher [Optional])
   ├─> SQL lọc cứng khách sạn theo thành phố, giá phòng, hạng sao -> trả về whitelist_ids (Bắt buộc)
   └─> Cypher quét Neo4j tìm khách sạn có kết nối tới Tags/Amenities mong muốn (Thử nghiệm)
   │
   ▼
Stage 3: Parallel Retrieval (Bất đồng bộ - Asyncio)
   ├─> Keyword Search (OpenSearch BM25): Tìm trên alias hotel_chunks + lọc whitelist_ids -> Top 50 Chunks
   └─> Semantic Search (Qdrant Vector DB): Tìm cosine similarity trên vector chunks + lọc whitelist_ids -> Top 50 Chunks
   │
   ▼
Stage 4: Score Fusion (Reciprocal Rank Fusion - RRF)
   └─> Hòa trộn thứ hạng từ BM25 (OpenSearch) và Vector Search (Qdrant) để chọn ra Top 15 ứng viên tốt nhất
   │
   ▼
Stage 5: Neural Re-ranking (Cross-Encoder Model local)
   └─> Sử dụng BAAI/bge-reranker-base chấm điểm mức độ liên quan ngữ nghĩa -> Top 5 Chunks gửi cho LLM
```

---

## 2. CÁC PHƯƠNG PHÁP THỬ NGHIỆM SO SÁNH (EXPERIMENTAL METHODS)

Để đưa ra quyết định kiến trúc chính xác và sớm nhất, chúng ta sẽ xây dựng nhanh hai cấu hình baseline để so sánh:

### Phương pháp A: Hybrid RAG Không dùng Graph (Postgres + OpenSearch + Vector + Reranker)

- **Hạ tầng:** PostgreSQL + OpenSearch 2.x + Qdrant + Reranker. Loại bỏ hoàn toàn Neo4j khỏi luồng.
- **Cơ chế:**
    1. PostgreSQL lọc cứng theo các thông số cấu trúc (giá, hạng sao, thành phố) để sinh ra `whitelist_ids` khách sạn hợp lệ.
    2. Chạy song song tìm kiếm OpenSearch BM25 và Vector Search trên không gian được giới hạn bởi `whitelist_ids`. Các ý định dạng phong cách hay tiện ích mờ (như *yên tĩnh, lãng mạn*) sẽ hoàn toàn dựa vào khả năng biểu diễn ngữ nghĩa của Vector DB để truy xuất.
    3. Trộn kết quả bằng RRF và chấm điểm lại qua Neural Reranker.
- **Đặc điểm:** Tinh giản cấu trúc hệ thống, giảm tải tài nguyên phần cứng, giảm độ trễ (latency) vì không cần truy vấn Neo4j.

### Phương pháp B: Graph-Enhanced Hybrid RAG (Postgres + Neo4j + OpenSearch + Vector + Reranker)

- **Hạ tầng:** PostgreSQL + Neo4j + OpenSearch 2.x + Qdrant + Reranker.
- **Cơ chế:**
    1. PostgreSQL lọc cứng thông số cơ bản. Song song đó, Neo4j thực hiện quét Cypher query để xác định các khách sạn thỏa mãn chính xác các mối quan hệ đồ thị với các tag tiện ích và phong cách (ví dụ: `(Hotel)-[:SUITABLE_FOR]->(Tag STYLE_QUIET)`). Kết quả của hai bộ lọc được giao nhau (intersection) để sinh ra danh sách `whitelist_ids` tối ưu.
    2. Tìm kiếm song song OpenSearch BM25 và Vector Search trên tập `whitelist_ids`.
    3. Trộn kết quả bằng RRF và chấm điểm lại qua Neural Reranker.
- **Đặc điểm:** Tận dụng tối đa mối quan hệ ngữ nghĩa có cấu trúc cứng của Ontology du lịch để giải quyết các ý định tiện ích chính xác, tuy nhiên tăng độ trễ và phức tạp hạ tầng.

---

## 3. PHÂN BỔ CÁC TASK CHI TIẾT THEO SPRINT

### SPRINT 1: Thiết Kế Nền Tảng, Môi Trường & POC Baselines (Tuần 1–2)

*Trạng thái: Đang thực hiện*

- **Task 1.1: Xây dựng Query Parser (Phân tích ý định - thử nghiệm với model local)**
    - **Hiện trạng:** Đã triển khai thành công hàm `parse_query_with_qwen` trong `test_retrieval.py` sử dụng model local `qwen2.5:7b` qua Ollama để trích xuất JSON có cấu trúc. Tích hợp cơ chế Rule-based Fallback tự động khi gọi Ollama bị timeout.
- **Task 1.2: Thiết lập Search Infra & Nạp Dữ Liệu POC**
    - **Hiện trạng:**
        - Thiết lập xong môi trường Docker gồm PostgreSQL, Neo4j 5.x, OpenSearch 2.11.1, và Qdrant.
        - Nạp thành công dữ liệu chuẩn hóa vào Postgres và đồng bộ đồ thị mối quan hệ sang Neo4j qua `ingest_data.py`.
        - Đồng bộ chunks sang OpenSearch qua `scripts/run_index.py` (hoặc `index_opensearch.py`).
        - Kết nối BM25: `http://localhost:9200`, index alias `hotel_chunks` (physical: `idx_hotel_chunks_v1.0` — xem doc Search Infra).
- **Task 1.3: Thiết lập 2 luồng Baseline sơ khởi cho các phương pháp thử nghiệm**
    - **Cách xử lý:**
        - **Baseline A (Hybrid không dùng Graph):** Thử nghiệm bỏ bước lọc đồ thị, chỉ dùng Postgres SQL lọc cứng tạo whitelist cho luồng tìm kiếm song song.
        - **Baseline B (Graph Hybrid RAG):** Hoàn thiện bộ chạy thử nghiệm tích hợp toàn bộ luồng bao gồm lọc đồ thị qua Neo4j Cypher.

---

### SPRINT 2: Benchmark Quyết Định Kiến Trúc & Phát Triển Tính Năng Tối Ưu (Tuần 3–4)

*Trạng thái: Đang thực hiện*

- **Task 2.1: Chạy Benchmark Baseline & Quyết định lựa chọn Kiến Trúc (MỚI - Ngay đầu Sprint 2)**
    - **Cách xử lý:** Sử dụng bộ test 50 queries Golden Dataset thực tế trong `[pipeline_nodes_io.json]` để chạy thử nghiệm độc lập trên hai cấu hình Baseline A (Không dùng Graph) và Baseline B (Có dùng Graph) đã được dựng sẵn từ Sprint 1. Đo lường chất lượng (**Recall@10**, **MRR**, **NDCG**) và hiệu năng (**Latency p95**).
    - **Output:** Báo cáo so sánh chi tiết [baseline_benchmark.md] làm cơ sở khoa học để **chốt ngay phương án kiến trúc cuối cùng** (Có giữ lại Neo4j hay không).
- **Task 2.2: Hoàn thiện bộ lọc Pre-Filtering tối ưu cho kiến trúc đã chọn**
    - **Cách xử lý:**
        - Nếu chọn Phương án A: Tối ưu hóa các query SQL và lập chỉ mục (index) cho bảng quan hệ trên Postgres.
        - Nếu chọn Phương án B: Chuẩn hóa các Cypher query khớp mối quan hệ trên Neo4j bằng cách sử dụng `toLower()`, kết hợp JOIN logic với Postgres SQL.
    - **Output:** Module `retrievers/pre_filter.py` được tối ưu hóa.
- **Task 2.3: Lập trình Bất Đồng Bộ Parallel Retrieval**
    - **Cách xử lý:** Chuyển đổi các hàm gọi đồng bộ của OpenSearch và Vector Search sang dạng bất đồng bộ sử dụng thư viện `opensearch-py` (`AsyncOpenSearch`) và `qdrant-client`. Sử dụng `asyncio.gather()` để chạy song song BM25 và Vector search với bộ lọc `whitelist_ids` nhằm giảm latency xuống tối thiểu.
    - **Output:** Module `retrievers/parallel_retriever.py` hỗ trợ truy vấn bất đồng bộ.
- **Task 2.4: Phát triển thuật toán trộn điểm RRF (Rank Fusion)**
    - **Cách xử lý:** Viết hàm nhận danh sách kết quả (Top 50) từ OpenSearch và Vector Search. Tính điểm RRF cho từng chunk và sắp xếp giảm dần để lấy Top 15 candidates.
    - **Output:** File `ranking/fusion.py` chứa hàm `reciprocal_rank_fusion()`.

---

### SPRINT 3: Neural Reranking, Đo Lường Đánh Giá Cuối Kỳ & Đóng Gói API (Tuần 5–6)

*Trạng thái: Kế hoạch*

- **Task 3.1: Tích hợp mô hình Neural Re-ranking**
    - **Cách xử lý:** Triển khai một Cross-Encoder hạng nhẹ chạy local trên CPU (ví dụ: `BAAI/bge-reranker-base`). Nhận 15 candidates từ RRF và Query gốc, chấm điểm tương thích ngữ nghĩa tuyệt đối, sau đó chọn ra Top 5 chunk cuối cùng có độ liên quan cao nhất.
    - **Output:** File `ranking/reranker.py` chứa hàm `re_rank_candidates()`.
- **Task 3.2: Đánh giá chất lượng cuối kỳ (Final Evaluation) & Tối ưu hóa**
    - **Cách xử lý:** Chạy kiểm thử tự động toàn bộ 50 queries trên kiến trúc đã chọn sau khi đã tích hợp Reranker. Đo lường lại chất lượng cuối cùng để đảm bảo hệ thống đạt mục tiêu Recall/MRR đề ra và kiểm tra SLO Latency dưới 500ms.
    - **Output:** Báo cáo nghiệm thu chất lượng tìm kiếm `final_retrieval_report.md`.
- **Task 3.3: Tích hợp API Endpoint**
    - **Cách xử lý:** Tạo class `SearchEngine` làm interface duy nhất với phương thức tìm kiếm được tối ưu hóa theo cấu trúc đã chọn. Đóng gói thành API bằng FastAPI phục vụ cho chatbot backend.
    - **Output:** Module `services/search_engine.py` hoàn chỉnh và sẵn sàng deploy.