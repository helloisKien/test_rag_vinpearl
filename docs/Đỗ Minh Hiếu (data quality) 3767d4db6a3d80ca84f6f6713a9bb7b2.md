# Đỗ Minh Hiếu (data quality)

# Clean Architecture — Kiến trúc tổng thể & Công nghệ

> Owner: Đỗ Minh Hiếu (Data Quality)

DA10 là **Nền tảng Tri thức & Truy xuất** (Knowledge & Retrieval Platform), gồm 8 layer từ thu thập dữ liệu đến API phục vụ downstream (DA09). Mỗi layer ánh xạ 1-1 với một thư mục trong repo.

ChatGPT Image Jun 4, 2026 at 04_24_41 PM.png

## Kiến trúc tổng thể

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                            L8 — API (api/)                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  Search API  │  │  Context API │  │Knowledge API │  │  Health API  │     │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘     │
│  Framework: FastAPI, Port: 8000                                              │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼───────────────────────────────────────────┐
│                    L7 — Context Construction (context/)                       │
│                                                                               │
│  Biến kết quả retrieval thành LLM-Ready Context Package:                      │
│  { context, citations, sources, metadata }                                   │
│                                                                               │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐                  │
│  │  Cite Selector │  │Context Builder │  │Metadata Merger │                  │
│  └────────────────┘  └────────────────┘  └────────────────┘                  │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼───────────────────────────────────────────┐
│                     L6 — Retrieval (retrieval/)                              │
│                                                                               │
│  ┌──────────────────────┐  ┌──────────────────────┐                          │
│  │   Vector Search      │  │   BM25 Lexical       │                          │
│  │   engine: Qdrant     │  │   engine: OpenSearch   │                          │
│  │   port: 6333         │  │   v2.11.1 · port 9200  │                          │
│  └──────────┬───────────┘  └──────────┬───────────┘                          │
│             │                         │                                       │
│             └──────────┬──────────────┘                                       │
│                        ▼                                                      │
│  ┌────────────────────────────────────────────┐                              │
│  │  Hybrid Fusion (RRF) + Re-ranker           │                              │
│  │  (Cross-encoder, threshold score fusion)   │                              │
│  └────────────────────────────────────────────┘                              │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼───────────────────────────────────────────┐
│                   L4 — Indexing (indexing/)                                  │
│                                                                               │
│  ┌──────────────────────┐  ┌──────────────────────┐                          │
│  │  Embedding           │  │  Inverted Index      │                          │
│  │  model: LLM embedder │  │  BM25 tokenization   │                          │
│  │  output: vectors     │  │  n-gram, analyzer    │                          │
│  └──────────┬───────────┘  └──────────┬───────────┘                          │
│             │                         │                                       │
│             ▼                         ▼                                       │
│        Qdrant                    OpenSearch                                   │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼───────────────────────────────────────────┐
│               L3 — Knowledge Engineering (knowledge_engineering/)             │
│                                                                               │
│  ┌──────────────────────┐  ┌──────────────────────�┐                          │
│  │  Document Chunking   │  │  Ontology Mapping    │                          │
│  │  ├── Sentence split  │  │  ├── Entity extract   │                          │
│  │  ├── Overlap window  │  │  ├── Relation map     │                          │
│  │  └── Token counting  │  │  └── Category tree    │                          │
│  └──────────────────────┘  └──────────────────────┘                          │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼───────────────────────────────────────────┐
│                L2 — Ingestion (ingestion/)                                   │
│                                                                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
│  │  Clean   │→ │  Dedup   │→ │ Validate │→ │  Export  │→ │  PostgreSQL  │   │
│  │(text +   │  │(MinHash  │  │(schema + │  │(DB)      │  │  (hotels,    │   │
│  │ amenity  │  │ + LSH)   │  │ quality) │  │          │  │  rooms,      │   │
│  │ + impute │  │          │  │          │  │          │  │  nearby,     │   │
│  │ + mock)  │  │          │  │          │  │          │  │  activity)   │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────────┘   │
│  Python scripts, data/cleaned/, data/quarantine/                              │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼───────────────────────────────────────────┐
│                    L1 — Data Sources (data/, crawler/)                       │
│                                                                               │
│  ┌──────────────────────┐  ┌──────────────────────┐                          │
│  │  Agoda Crawler       │  │  External APIs       │                          │
│  │  ├── hotel list      │  │  ├── Google Places   │                          │
│  │  ├── hotel detail    │  │  └── ...             │                          │
│  │  └── hotel faq       │  │                      │                          │
│  └──────────┬───────────┘  └──────────────────────┘                          │
│             │                                                                 │
│             ▼                                                                 │
│  data/raw/hotels/*.json (JSON files từ Agoda)                                │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Luồng dữ liệu

```
crawler/ ──▶ ingestion/ ──▶ knowledge_engineering/ ──▶ indexing/
                                                           │
                                                           ▼
api/ ◀── context/ ◀── retrieval/ ◀────────────── (chỉ mục vector + BM25)
```

Pipeline chi tiết Layer 2 (Ingestion):

```
data/raw/hotels/*.json
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  1. Cleaning (scripts/clean_pipeline.py)                     │
│                                                              │
│  ┌───────────────────────────────────────────────────────┐   │
│  │  A. Xử lý văn bản (cho mọi text field)                │   │
│  │  ├── strip_html()      – BeautifulSoup strip HTML     │   │
│  │  ├── normalize_text()  – Unicode NFC + emoji remove    │   │
│  │  └── translate_to_vi() – Deep-Translator → Google     │   │
│  │      (chỉ cho review response không phải tiếng Việt)  │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌───────────────────────────────────────────────────────┐   │
│  │  B. Amenity Normalizer (amenity_normalizer.py)         │   │
│  │  (6 bước: strip bracket → clean text → canonical      │   │
│  │   prefix → fuzzy merge → filter basic → filter gen.)  │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌───────────────────────────────────────────────────────┐   │
│  │  C. Max Occupancy Imputer (occupancy_imputer.py)       │   │
│  │  ├── max_occupancy_raw → max_occupancy_text            │   │
│  │  ├── Parse bed_type / bed_types (số lượng + loại)      │   │
│  │  └── Fallback 2 người                                  │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                              │
│  ┌───────────────────────────────────────────────────────┐   │
│  │  D. Price Mocker (price_mocker.py)                     │   │
│  │  ├── price_per_night = base(stars) × brand × room     │   │
│  │  │   × city × size (deterministic, clamp star range)  │   │
│  │  └── original_price = price × discount (MD5 hash)     │   │
│  └───────────────────────────────────────────────────────┘   │
│                                                              │
│  Áp dụng cho: amenities, amenities_general/_leisure/_dining,│
│  room_amenities, rooms, room_grid.rooms                      │
└──────────────────────────────┬────────────────────────────┘
                               ▼
                       data/cleaned/hotel_{id}.json
                               │
                               ▼
┌──────────────────────────────────────────────────────────┐
│  2. Deduplication (scripts/dedup_pipeline.py)            │
│  ├── MinHash + LSH (datasketch)                          │
│  ├── threshold Jaccard ≥ 0.85, 128 permutations          │
│  ├── Language-agnostic (character 5-gram)                │
│  └── Verify bằng exact Jaccard sau LSH query            │
└──────────────────────────────┬───────────────────────────┘
                               ▼
                       data/cleaned/hotel_{id}.json  (ghi đè)
                       data/dedup_groups.json
                               │
                               ▼
┌──────────────────────────────────────────────────────────┐
│  3. Validation (scripts/validation_pipeline.py)          │
│  ├── schema_validator: validate theo data_schema.json    │
│  │   (required fields, numeric range, format, alias id)  │
│  ├── quality_checks: Missing Rate & Duplicate Rate       │
│  └── Quarantine: invalid docs → data/quarantine/         │
└──────────────────────────────┬───────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────┐
│  4. Export → PostgreSQL (scripts/export_db.py)            │
│  ├── Tạo bảng (Alembic migration)                        │
│  ├── INSERT 4 bảng: hotels, rooms, nearby_places,        │
│  │   activities                                           │
│  └── Dedup composite PK trước khi insert                 │
└──────────────────────────────────────────────────────────┘
                               │
                               ▼
                   PostgreSQL (localhost:5432)
                   docs/data_quality_report.md
```

## Chi tiết các Layer

### L1 — Data Sources (`data/`, `crawler/`)

Nơi chứa dữ liệu thô từ Agoda (crawler output) và các nguồn bên ngoài.


| Thành phần      | File / Folder                | Mô tả                               |
| --------------- | ---------------------------- | ----------------------------------- |
| Hotel raw       | `data/raw/hotels/*.json`     | ~100+ hotel JSON từ Agoda           |
| Crawler scripts | `crawler/`                   | Selenium + Requests crawl Agoda API |
| Format          | JSON (Agoda property detail) | Rất nhiều biến thể cấu trúc         |


Lưu ý: Dữ liệu raw có thể có nhiều vấn đề — HTML tags, unicode lỗi, emoji, amenities dạng string lẫn array, price null, thiếu max_occupancy. Các vấn đề này được xử lý ở Layer 2.

### L2 — Ingestion (`ingestion/`)

Pipeline 4 bước: **Clean → Dedup → Validate → Export → PostgreSQL**.

### `ingestion/cleaning/text_normalizer.py`


| Function                  | Kỹ thuật                       | Mô tả                    |
| ------------------------- | ------------------------------ | ------------------------ |
| `normalize_unicode()`     | `unicodedata.normalize("NFC")` | Chuẩn hóa dấu tiếng Việt |
| `remove_control_chars()`  | Regex `[\x00-\x08...]`         | Loại bỏ ký tự điều khiển |
| `collapse_whitespace()`   | Regex multi-space/newline      | Chuẩn hóa khoảng trắng   |
| `normalize_punctuation()` | Replace Unicode → ASCII        | Dấu nháy, gạch ngang, …  |
| `remove_emoji()`          | Regex Unicode block            | Loại bỏ icon/emoji       |
| `normalize_text()`        | Combine all above              | Pipeline tổng hợp        |


### `ingestion/cleaning/html_stripper.py`

- Dùng BeautifulSoup strip HTML tags → plain text
- Extract `image_urls` + `links` từ thẻ `<img>` và `<a>`

### `ingestion/cleaning/amenity_normalizer.py`

Quy trình 6 bước xử lý amenities:


| Step                | Kỹ thuật                         | Input                                                                      | Output                             |
| ------------------- | -------------------------------- | -------------------------------------------------------------------------- | ---------------------------------- |
| 1. Strip brackets   | Regex `\[` / `\]` / `\(` / `\)`  | `Wi-Fi [miễn phí]`                                                         | `Wi-Fi miễn phí`                   |
| 2. Clean text       | Unicode + suffix removal         | `Wi-Fi miễn phí`                                                           | `wi-fi miễn phí`                   |
| 3. Canonical prefix | Regex pattern matching           | `wi-fi miễn phí` → `WiFi miễn phí`                                         | Chỉ thay prefix                    |
| 4. Fuzzy merge      | `difflib.SequenceMatcher` (0.80) | `nước đóng chai` + `nước đóng chai miễn phí`                               | `Nước đóng chai miễn phí`          |
| 5. Filter basic     | Regex pattern list               | `Tiện nghi` → ❌, `Máy sấy tóc` → ❌                                         | 41 basic items removed             |
| 6. Filter generic   | Smart word-prefix                | `WiFi` → ❌ (nếu có `WiFi miễn phí`); `TV` → ❌ (nếu có `TV màn hình phẳng`) | Chỉ remove khi có specific variant |


### `ingestion/cleaning/translator.py`

- Dùng `deep-translator` (Google Translate engine)
- Cache theo text gốc để tránh dịch lại
- Heuristic detect tiếng Việt (kiểm tra ký tự có dấu)
- Chỉ dịch các field `text`, `title`, `positives`, `negatives`, `response` trong review comments

### `ingestion/cleaning/occupancy_imputer.py`

**Vấn đề:** Crawler không thu thập được `max_occupancy` cho ~90% rooms (đặc biệt là Muong Thanh hotels).

**Giải pháp:** Impute `max_occupancy` qua fallback chain 4 bước:

```
Bước 1: Dùng room.max_occupancy nếu đã có (> 0)
  Ví dụ: Vinpearl rooms → max_occupancy = 3 (giữ nguyên)

Bước 2: Parse room.max_occupancy_text nếu có
  Regex: r"(\d+)" → tìm số đầu tiên
  Ví dụ: "Tối đa 3 người lớn" → 3
         "8 người" → 8

Bước 3: Parse bed_types[] hoặc bed_type nếu 2 bước trên đều null
  Regex từng nhóm: (\d+)\s+giường\s+(loại giường)

  Map loại giường → sức chứa:

  | Loại giường | Sức chứa |
  |---|---|
  | đơn, semi-double | 1 |
  | đôi, lớn, đôi lớn, siêu lớn, king, queen | 2 |
  | tầng (bunk bed) | 2 |
  | sofa giường | 1 |

  Xử lý kết hợp (AND): từ khóa "và" hoặc ","
    "1 giường lớn và 2 giường đơn" → (1 × 2) + (2 × 1) = 4

  Xử lý hoặc (OR): từ khóa "/" hoặc "hoặc"
    "1 giường đôi lớn / 1 giường lớn" → max(2, 2) = 2

  Ví dụ cụ thể:

  | bed_type | Parse | Kết quả |
  |---|---|---|
  | "1 giường lớn" | 1 × 2 (lớn) | 2 |
  | "2 giường đơn" | 2 × 1 (đơn) | 2 |
  | "1 giường đôi" | 1 × 2 (đôi) | 2 |
  | "3 giường đơn" | 3 × 1 (đơn) | 3 |
  | "1 giường siêu lớn" | 1 × 2 (siêu lớn) | 2 |
  | "1 giường lớn và 2 giường đơn" | 2 + 2 | 4 |
  | "1 giường đôi lớn / 1 giường lớn" | max(2, 2) | 2 |
  | null / empty | — | fallback 2 |

Bước 4: Fallback = 2 (đa số phòng khách sạn chứa 2 người)
```

**Kết quả:** 463 rooms — 0% null max_occupancy ✅

### `ingestion/cleaning/price_mocker.py`

**Vấn đề:** Agoda API (`/api/v1/property/room-grid`) không trả giá phòng. Giá được load dynamic bằng JavaScript, crawler không với tới được.

**Giải pháp:** Tạo giá giả (mock) dựa trên đặc điểm của hotel và room, sử dụng MD5 hash để đảm bảo deterministic — cùng hotel_id + room_type_id → luôn ra cùng một giá.

**Công thức `price_per_night`:**

```
price = base_mid(stars)
price × brand_factor
price × room_type_factor
price × city_factor
price × size_factor

price = clamp(base_min, base_max)        // giới hạn trong khung sao
price = round(price ÷ 10.000) × 10.000   // làm tròn đến 10k
```

**Bảng giá cơ sở (VND):**


| Star rating  | Min (base_min)          | Mid (base_mid) | Max (base_max) |
| ------------ | ----------------------- | -------------- | -------------- |
| 5★           | 2.000.000               | 3.500.000      | 5.000.000      |
| 4★           | 1.200.000               | 2.100.000      | 3.000.000      |
| 3★           | 600.000                 | 1.050.000      | 1.500.000      |
| 2★           | 300.000                 | 550.000        | 800.000        |
| 1★           | 200.000                 | 350.000        | 500.000        |
| Không có sao | 600.000 (default về 3★) |                |                |


**Brand factor:**


| Tên chứa                        | Factor | Ví dụ                      |
| ------------------------------- | ------ | -------------------------- |
| “Vinpearl” hoặc “Meliá”/“Melia” | 1.2×   | Vinpearl Resort Nha Trang  |
| “Muong Thanh”                   | 0.9×   | Mường Thanh Sài Gòn Centre |
| Còn lại (Boutique, Homestay, …) | 0.8×   | Robins Homestay            |


**Room type factor:**


| Tên phòng chứa | Factor | Ví dụ              |
| -------------- | ------ | ------------------ |
| “Penthouse”    | 2.0×   | Penthouse Suite    |
| “Suite”        | 1.8×   | Executive Suite    |
| “Villa”        | 1.6×   | Villa Hồ Bơi       |
| “Studio”       | 1.4×   | Studio Căn Hộ      |
| “Deluxe”       | 1.3×   | Deluxe King Room   |
| “Executive”    | 1.3×   | Executive Room     |
| “Premier”      | 1.2×   | Premier Ocean View |
| “Family”       | 1.1×   | Family Room        |
| “Superior”     | 1.0×   | Superior Double    |
| “Standard”     | 0.9×   | Standard Twin      |
| Không match    | 1.0×   | —                  |


**City factor:**


| City chứa                                              | Factor | Lý do                         |
| ------------------------------------------------------ | ------ | ----------------------------- |
| “Phú Quốc”, “Nha Trang”, “Hạ Long”                     | 1.3×   | Điểm đến du lịch biển cao cấp |
| “Đà Nẵng”, “Hội An”, “Sầm Sơn”, “Phan Thiết”, “Đà Lạt” | 1.1×   | Điểm đến du lịch phổ biến     |
| Còn lại                                                | 1.0×   | —                             |


**Size factor:**

```
size_factor = max(0.5, min(2.0, sqm / 30))
```

Với 30m² là diện tích chuẩn. Phòng 15m² → factor = 0.5, phòng 60m² → factor = 2.0.
Nếu không có `size_sqm`, parse từ `room_size` (vd: “45 m²” → 45). Nếu không có → factor = 1.0.

**Công thức `original_price`:**

```python
key = f"{hotel_id}_{room_type_id}"
hash_hex = MD5(key.encode()).hexdigest()[:8]
hash_int = int(hash_hex, 16)

discount = 1.2 + (hash_int % 6000) / 10000
# discount luôn nằm trong khoảng [1.20, 1.80]

original_price = round(price_per_night × discount ÷ 10.000) × 10.000
```

**Ví dụ tính toán — Vinpearl Resort Nha Trang (5★), Room: Deluxe King (32m²):**

```
base_mid = 3.500.000
× brand (Vinpearl)       1.2   → 4.200.000
× room (Deluxe)          1.3   → 5.460.000
× city (Nha Trang)       1.3   → 7.098.000
× size (32/30 = 1.067)  1.067 → 7.571.200

clamp(2.000.000, 5.000.000) → 5.000.000
round 10k                    → 5.000.000  (= price_per_night)

key = "65153_13678787"
MD5 hex[:8] = "a1b2c3d4" → int = 2712849104
discount = 1.2 + (2712849104 % 6000) / 10000
         = 1.2 + 0.4704 = 1.6704

original = 5.000.000 × 1.6704 = 8.352.000 → round 10k → 8.350.000
```

### `ingestion/deduplication/minhash.py`

- `datasketch` MinHash + LSH
- 128 permutations, Jaccard threshold ≥ 0.85
- Character 5-gram, language-agnostic
- Verify bằng exact Jaccard sau LSH query

### `ingestion/validation/schema_validator.py`

- Validate hotel docs theo `contracts/data_schema.json` (DA09’s PostgreSQL schema)
- 4 bảng: hotels, rooms, nearby_places, activities
- Alias `id` ↔︎ `hotel_id` (Agoda dùng `hotel_id`)
- Sub-document FK `hotel_id` implicit nếu parent có ID
- Numeric range checks, format checks (ISO 8601)

### `ingestion/validation/quality_checks.py`


| Metric         | Target | Công thức                                |
| -------------- | ------ | ---------------------------------------- |
| Missing Rate   | < 5%   | `missing_fields / total_required_fields` |
| Duplicate Rate | < 2%   | `duplicate_docs / total_docs`            |


### L3 — Knowledge Engineering (`knowledge_engineering/`)

Layer chịu trách nhiệm chunking document và mapping ontology.


| Thành phần        | Mô tả                                                |
| ----------------- | ---------------------------------------------------- |
| Document Chunking | Sentence splitting + overlap window + token counting |
| Ontology Mapping  | Entity extraction, relation mapping, category tree   |


Dữ liệu đầu vào: cleaned JSON từ PostgreSQL hoặc `data/cleaned/`.
Dữ liệu đầu ra: chunks sẵn sàng cho embedding.

### L4 — Indexing (`indexing/`)

Tạo vector embedding và inverted index.


| Thành phần     | Công nghệ                     | Mô tả                                 |
| -------------- | ----------------------------- | ------------------------------------- |
| Embedding      | LLM embedder                  | Chuyển chunks → vectors               |
| Vector DB      | Qdrant (port 6333)            | Lưu vectors, cosine similarity search |
| Inverted Index | OpenSearch 2.11.1 (port 9200) | BM25 lexical search                   |
| Index Script   | `scripts/run_index.py`        | Orchestrate indexing pipeline         |


### L6 — Retrieval (`retrieval/`)

Truy xuất hybrid (vector + BM25) + re-ranking.


| Thành phần       | Mô tả                            |
| ---------------- | -------------------------------- |
| Vector Search    | Qdrant client, cosine similarity |
| BM25 Lexical     | OpenSearch client, text query    |
| Hybrid Fusion    | RRF (Reciprocal Rank Fusion)     |
| Re-ranker        | Cross-encoder model              |
| Retrieval Script | `scripts/run_eval.py`            |


### L7 — Context Construction (`context/`)

Xây dựng gói ngữ cảnh cho LLM.


| Thành phần      | Mô tả                                     |
| --------------- | ----------------------------------------- |
| Cite Selector   | Chọn citations từ retrieval results       |
| Context Builder | Ghép context từ các chunks được chọn      |
| Metadata Merger | Gom metadata (sources, scores, positions) |


Output: LLM-Ready Context Package `{ context, citations, sources, metadata }`.

### L8 — API (`api/`)

FastAPI server phục vụ downstream (DA09).


| Endpoint          | Mô tả                        |
| ----------------- | ---------------------------- |
| `GET /search`     | Search + retrieval + context |
| `GET /context`    | Build context từ query       |
| `POST /knowledge` | Knowledge query              |
| `GET /health`     | Health check                 |


Port: `8000`, Docker container `api`.

## Công nghệ sử dụng

### Storage


| Thành phần  | Công nghệ         | Port | Mục đích                     |
| ----------- | ----------------- | ---- | ---------------------------- |
| Database    | PostgreSQL 16     | 5432 | Lưu cleaned structured data  |
| Vector DB   | Qdrant            | 6333 | Vector search (embeddings)   |
| Text Search | OpenSearch 2.11.1 | 9200 | BM25 lexical search          |
| Migration   | Alembic           | —    | Quản lý PostgreSQL schema    |
| ORM         | SQLAlchemy        | —    | Python ↔︎ PostgreSQL mapping |


### Data Pipeline


| Module               | Library                   | Use case                                 |
| -------------------- | ------------------------- | ---------------------------------------- |
| HTML stripping       | BeautifulSoup             | Loại bỏ HTML tags khỏi text              |
| Unicode NFC          | `unicodedata` (built-in)  | Chuẩn hóa dấu tiếng Việt                 |
| Emoji removal        | Regex Unicode block       | Loại bỏ icon trong review                |
| Regex cleaning       | `re` (built-in)           | Strip brackets, normalize punctuation    |
| Canonical mapping    | Regex pattern match       | Gom amenity cùng loại                    |
| Fuzzy merge          | `difflib.SequenceMatcher` | Gom amenity tương tự                     |
| Translation          | `deep-translator`         | Dịch review response → tiếng Việt        |
| MinHash LSH          | `datasketch`              | Near-duplicate detection                 |
| Schema validation    | Custom dataclass          | Kiểm định required fields, range, format |
| Occupancy imputation | Regex + heuristics        | Fill max_occupancy từ bed_type           |
| Price mocking        | MD5 hash (deterministic)  | Tạo giá giả cho room                     |
| JSON processing      | `orjson`                  | Fast JSON read/write                     |


### DevOps


| Thành phần        | Công nghệ               |
| ----------------- | ----------------------- |
| Container runtime | Docker + Docker Compose |
| API Framework     | FastAPI (Python)        |
| Version control   | Git + GitHub            |
| Data format       | JSON (raw + cleaned)    |


## So sánh kỹ thuật


| Kỹ thuật                 | Library                   | Use case                                 | Ưu điểm                                       | Nhược điểm                                          |
| ------------------------ | ------------------------- | ---------------------------------------- | --------------------------------------------- | --------------------------------------------------- |
| **HTML stripping**       | BeautifulSoup             | Loại bỏ HTML tags khỏi text              | Chính xác, xử lý nested tags tốt              | Chậm hơn regex thuần                                |
| **Unicode NFC**          | `unicodedata` (built-in)  | Chuẩn hóa dấu tiếng Việt                 | Built-in, zero dependency, nhanh              | Không xử lý các dạng tổ hợp đặc biệt                |
| **Emoji removal**        | Regex Unicode block       | Loại bỏ icon trong review                | Không cần thêm dependency                     | Không bắt được 100% emoji mới                       |
| **Regex cleaning**       | `re` (built-in)           | Strip brackets, normalize punctuation    | Nhanh, dễ maintain                            | Không linh hoạt với pattern phức tạp                |
| **Canonical mapping**    | Regex pattern match       | Gom amenity cùng loại                    | Kiểm soát được, dễ thêm mapping               | Không tự học được biến thể mới                      |
| **Fuzzy merge**          | `difflib.SequenceMatcher` | Gom amenity tương tự                     | Không cần training data, threshold chỉnh được | Threshold khó chọn, false positive với prefix chung |
| **Translation**          | `deep-translator`         | Dịch review → tiếng Việt                 | Free, không cần API key                       | Rate-limit, phụ thuộc internet                      |
| **MinHash LSH**          | `datasketch`              | Near-duplicate detection                 | Scale tốt với hàng triệu doc                  | Xác suất (cần verify exact Jaccard)                 |
| **Schema validation**    | Custom dataclass          | Kiểm định required fields, range, format | Tùy chỉnh được theo schema                    | Phải maintain schema đồng bộ DA09                   |
| **Occupancy imputation** | Regex + heuristics        | Fill max_occupancy từ bed_type           | Zero dependency                               | Không chính xác với bed_type lạ                     |
| **Price mocking**        | Deterministic MD5         | Tạo giá giả cho room                     | Deterministic, tái lập được                   | Giá không real (mock data)                          |


## Deployment Architecture

```yaml
# docker-compose.yml — chi tiết OpenSearch/Qdrant: doc Search Infra (Lê Hoàng Đạt) §7
services:
  api:        # FastAPI — port 8000
  postgres:   # PostgreSQL 16 — port 5432
  qdrant:     # Vector DB — port 6333 (qdrant/qdrant:v1.8.0)
  opensearch: # BM25 — port 9200 (opensearchproject/opensearch:2.11.1)
```

```bash
# Khởi động toàn bộ services
docker compose up -d

# Pipeline ingestion (layer 2)
alembic upgrade head
python scripts/run_ingest.py
```

## Design Decisions


| Decision                             | Lựa chọn          | Lý do                                                         |
| ------------------------------------ | ----------------- | ------------------------------------------------------------- |
| PostgreSQL thay vì DuckDB            | PostgreSQL        | Yêu cầu real-time data sharing; DuckDB phù hợp OLAP           |
| MinHash + LSH thay vì exact dedup    | MinHash           | Scalable với số lượng document lớn                            |
| `difflib.SequenceMatcher` thay vì ML | SequenceMatcher   | Không cần training data, threshold controllable               |
| Deterministic mock price via MD5     | MD5 hash          | Reproducible, thay thế `random`                               |
| 4-step fallback cho occupancy        | Heuristics        | Zero dependency, không cần external service                   |
| JSON cleaning thay vì DB cleaning    | File-based        | Dễ debug, inspect dữ liệu sau mỗi bước                        |
| Qdrant cho vector search             | Qdrant            | Lightweight, Docker-native, REST API                          |
| OpenSearch 2.x cho BM25              | OpenSearch 2.11.1 | Apache 2.0, team chốt thống nhất DA10; client `opensearch-py` |
| FastAPI cho API layer                | FastAPI           | Async, auto OpenAPI docs, type validation                     |


## Kết quả hiện tại (Layer 2)


| Metric                       | Giá trị                | Target | Kết quả |
| ---------------------------- | ---------------------- | ------ | ------- |
| Total documents              | 51                     | –      | –       |
| Missing rate                 | 0.0%                   | < 5.0% | ✅       |
| Duplicate rate               | 0.0%                   | < 2.0% | ✅       |
| Amenity trung bình/hotel     | ~81 (giảm từ ~167 raw) | –      | –       |
| Validation errors            | 0                      | –      | ✅       |
| Null max_occupancy (rooms)   | 0/463                  | –      | ✅       |
| Null price_per_night (rooms) | 0/463                  | –      | ✅       |
| PostgreSQL hotels            | 51                     | –      | ✅       |
| PostgreSQL rooms             | 463                    | –      | ✅       |
| PostgreSQL nearby_places     | 497                    | –      | ✅       |
| PostgreSQL activities        | 507                    | –      | ✅       |


## Hướng dẫn chạy

### Lần đầu (khởi tạo toàn bộ hệ thống)

```bash
# 1. Khởi động services
docker compose up -d

# 2. Tạo bảng PostgreSQL
alembic upgrade head

# 3. Chạy ingestion pipeline (clean → dedup → validate → export)
python scripts/run_ingest.py

# 4. (TODO) Chạy indexing (chunk → embed → index)
# python scripts/run_index.py

# 5. (TODO) Chạy API server
# docker compose up -d api
```

### Chạy lại (khi có data crawl mới)

```bash
# Chạy full pipeline ingestion
python scripts/run_ingest.py

# Skip các bước đã chạy
python scripts/run_ingest.py --skip-clean --skip-dedup  # chỉ validate + db
```

### Kiểm tra dữ liệu PostgreSQL

```bash
docker compose exec postgres psql -U da10 -d da10

# Ví dụ query
SELECT name, city, review_score FROM hotels LIMIT 5;
SELECT COUNT(*) FROM rooms;
```

## Tham chiếu


| File                         | Vai trò                                           |
| ---------------------------- | ------------------------------------------------- |
| `docker-compose.yml`         | Service orchestration                             |
| `contracts/data_schema.json` | JSON schema giữa DA09 và DA10                     |
| `docs/04_ingestion.md`       | Chi tiết Layer 2 pipeline                         |
| `docs/database_usage.md`     | PostgreSQL connection & query guide               |
| `docs/relational_schema.md`  | Schema gốc từ DA09                                |
| `db/__init__.py`             | SQLAlchemy engine + session                       |
| `db/models.py`               | 4 ORM models (Hotel, Room, NearbyPlace, Activity) |
| `scripts/run_ingest.py`      | Entry point pipeline                              |
