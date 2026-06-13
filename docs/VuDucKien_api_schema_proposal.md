# API Schema Đề Xuất — DA10 OTA AI Search Platform

> Tài liệu này đề xuất request/response schema cho **SearchAPI** và **ContextAPI**.
> Schema được căn chỉnh để **chỉ phụ thuộc vào các bảng PostgreSQL hiện có** trong
> `relational_schema.md`: `hotels`, `rooms`, `nearby_places`, `activities`,
> và bảng `text_chunks` (sẽ được thêm vào để hỗ trợ vector search).
>
> Không sử dụng Neo4j, không sử dụng các field chưa có cột trong DB hiện tại.

---

## Quy ước chung


| Quy ước            | Mô tả                                |
| ------------------ | ------------------------------------ |
| Kiểu dữ liệu       | TypeScript-like cho dễ đọc           |
| `?` sau tên field  | Optional (có thể null/bỏ qua)        |
| `//`               | Chú thích giải thích nguồn gốc field |
| Đơn vị giá         | VND (integer)                        |
| Đơn vị khoảng cách | km (float)                           |
| Ngôn ngữ query     | Tiếng Việt (có thể bỏ dấu)           |


---

## 1. SEARCH API

**Endpoint:** `POST /api/v1/search`

**Mục đích:** Nhận query tự nhiên, trả về danh sách khách sạn đã được xếp hạng theo relevance.

---

### 1.1 Request Schema

```typescript
interface SearchRequest {

  // ── Bắt buộc ──────────────────────────────────────────────────────────────
  query: string
  // Câu hỏi tự nhiên của người dùng, tiếng Việt, có thể bỏ dấu.
  // Ví dụ: "tìm chỗ chill chill ở Đà Nẵng", "resort yên tĩnh gần biển"
  // Dùng bởi: Intent Parsing (LLM model) → Hybrid Search

  // ── Phân trang ────────────────────────────────────────────────────────────
  top_k?: number           // Số kết quả trả về, default: 10, max: 50
  page?: number            // Trang (0-indexed), default: 0
  // Lưu ý: phân trang phía sau RRF+rerank (trên kết quả đã xếp hạng)

  // ── Hard filters — do người dùng chọn rõ ràng từ UI bộ lọc ───────────────
  filters?: {
    city?: string            // Lọc theo cột hotels.city
                             // Ví dụ: "Đà Nẵng", "Nha Trang", "Houston (TX)"

    star_rating?: {
      min?: number           // Lọc theo cột hotels.star_rating (NUMERIC 3,1)
      max?: number           // Phạm vi 1.0 – 5.0
    }

    price?: {
      min?: number           // Lọc theo cột rooms.price (NUMERIC 15,2)
      max?: number           // VND, integer
    }

    accommodation_type?: string[]
    // Lọc theo cột hotels.accommodation_type (VARCHAR 100)
    // Ví dụ: ["Khách sạn", "Resort", "Biệt thự", "Homestay"]
    // → OR logic trong cùng array

    amenities?: string[]
    // Lọc theo cột hotels.amenities (TEXT[])
    // Ví dụ: ["Bể bơi ngoài trời", "Bãi biển riêng", "Spa"]
    // → AND logic (phải có tất cả) — dùng toán tử array của PostgreSQL

    suitable_for?: string[]
    // Lọc theo cột hotels.suitable_for (TEXT[])
    // Ví dụ: ["Cặp đôi", "Gia đình có trẻ nhỏ", "Khách đi công tác"]
    // → OR logic

    review_score?: {
      min?: number           // Lọc theo cột hotels.review_score, phạm vi 1.0 – 10.0
    }

    is_luxury?: boolean      // Lọc theo cột hotels.is_luxury (BOOLEAN)

    geo?: {
      lat: number            // Dùng kèm hotels.latitude / longitude
      lng: number
      radius_km: number      // Bán kính tìm kiếm địa lý
    }
  }

  // ── Tùy chọn kết quả ──────────────────────────────────────────────────────
  options?: {
    include_debug?: boolean
    // Nếu true → response bao gồm debug_info (parsed_intent, retrieval_scores).
    // Dùng cho dev/QA, tắt trên production.
  }
}
```

**Ví dụ Request:**

```json
{
  "query": "tìm chỗ chill chill yên tĩnh gần biển cho 2 người",
  "top_k": 10,
  "filters": {
    "city": "Đà Nẵng",
    "price": { "max": 3000000 },
    "suitable_for": ["Cặp đôi"]
  },
  "options": {
    "include_debug": false
  }
}
```

---

### 1.2 Response Schema

```typescript
interface SearchResponse {

  // ── Meta của request ──────────────────────────────────────────────────────
  query_id: string           // UUID để trace request, link với ContextAPI
  query: string              // Echo lại query gốc
  total_found: number        // Tổng số KS thoả filter (trước khi top_k)
  returned: number           // Số KS thực tế trong response này (≤ top_k)
  page: number

  latency_ms: number         // Tổng latency pipeline (mục tiêu p95 < 500ms)

  // ── Danh sách kết quả ─────────────────────────────────────────────────────
  results: HotelCard[]

  // ── Intent đã phân tích (luôn trả về để client hiểu system làm gì) ────────
  parsed_intent: ParsedIntent

  // ── Debug (chỉ có khi options.include_debug = true) ───────────────────────
  debug_info?: DebugInfo
}


// ─────────────────────────────────────────────────────────────────────────────
// HotelCard — thông tin hiển thị trên trang kết quả tìm kiếm
// (Chỉ chứa các field có trong bảng hotels, rooms, nearby_places)
// ─────────────────────────────────────────────────────────────────────────────
interface HotelCard {

  // ── Định danh (từ bảng hotels) ────────────────────────────────────────────
  hotel_id: number             // hotels.id
  name: string                 // hotels.name
  accommodation_type: string   // hotels.accommodation_type

  // ── Vị trí (từ bảng hotels) ───────────────────────────────────────────────
  address: string              // hotels.address
  city: string                 // hotels.city
  latitude: number             // hotels.latitude
  longitude: number            // hotels.longitude

  // ── Đánh giá (từ bảng hotels) ─────────────────────────────────────────────
  star_rating: number          // hotels.star_rating, phạm vi 1.0 – 5.0
  review_score: number         // hotels.review_score, phạm vi 1.0 – 10.0
  review_count: number         // hotels.review_count

  is_luxury: boolean           // hotels.is_luxury

  // ── Giá (từ bảng rooms) ───────────────────────────────────────────────────
  price_from: number           // MIN(rooms.price) WHERE rooms.hotel_id = hotels.id
                               // VND/đêm — giá thấp nhất trong các loại phòng

  // ── Nội dung (từ bảng hotels) ─────────────────────────────────────────────
  description: string          // hotels.description (cắt còn ~200 ký tự cho card)
  suitable_for: string[]       // hotels.suitable_for (TEXT[])

  // ── Tiện nghi nổi bật (từ bảng hotels.amenities) ──────────────────────────
  amenities_top: string[]
  // Subset 5-8 phần tử đầu của hotels.amenities (TEXT[]), ưu tiên các tiện nghi
  // liên quan đến query (ví dụ query "chill" → ưu tiên "Bể bơi", "Spa")

  // ── Ảnh (từ bảng hotels) ──────────────────────────────────────────────────
  thumbnail_url: string        // hotels.images[0]
  image_count: number          // array_length(hotels.images, 1)

  // ── Điểm xếp hạng từ pipeline ─────────────────────────────────────────────
  ranking: {
    final_score: number        // Score tổng hợp cuối cùng (0.0 – 1.0), dùng để sort
    rank: number               // Thứ hạng trong kết quả (1-indexed)

    relevance_score: number    // Score từ reranker model
    // Đo mức độ liên quan ngữ nghĩa giữa query và nội dung KS
    // (Giải thích "vì sao recommend" thuộc DA09, không trả về ở SearchAPI)
  }

  // ── Địa điểm lân cận (từ bảng nearby_places) ──────────────────────────────
  nearby_places?: {
    name: string               // nearby_places.name
    type: string               // nearby_places.type
    distance_km: number        // nearby_places.distance_km
  }[]
  // Subset 3-5 địa điểm gần nhất, ưu tiên theo type liên quan đến query

  // ── Link (từ bảng hotels) ─────────────────────────────────────────────────
  source_url: string           // hotels.source_url
}


// ─────────────────────────────────────────────────────────────────────────────
// ParsedIntent — kết quả phân tích intent từ query
// ─────────────────────────────────────────────────────────────────────────────
interface ParsedIntent {
  // Trích xuất bởi LLM model + rule-based fallback

  original_query: string
  normalized_query: string     // Sau normalize (thêm dấu, lowercase)

  hard_filters: {              // Các ràng buộc cứng LLM model trích từ query
    city?: string              // Map vào hotels.city
    star_rating?: { min?: number; max?: number }
    price?: { min?: number; max?: number }
  }

  keyword_expansion: string[]
  // Từ khóa mở rộng cho BM25
  // Ví dụ "yên tĩnh" → ["peaceful", "calm", "quiet", "tĩnh lặng", "vắng"]

  intent_type: "hotel_search" | "destination_info" | "comparison" | "faq" | "unclear"
  // Phân loại intent để route đúng pipeline

  confidence: number           // 0.0 – 1.0, độ tin cậy của parsing
  parsed_by: "llm" | "rule_based"  // Dùng để debug khi fallback
}


// ─────────────────────────────────────────────────────────────────────────────
// DebugInfo — chỉ có khi include_debug = true
// ─────────────────────────────────────────────────────────────────────────────
interface DebugInfo {
  stage_latencies: {
    intent_parsing_ms: number
    sql_prefilter_ms: number   // Lọc trên PostgreSQL theo filters
    parallel_retrieval_ms: number
    rrf_fusion_ms: number
    reranking_ms: number
  }

  whitelist_hotel_count: number  // Số KS qua được SQL filter
  bm25_candidates: number        // Số chunk từ OpenSearch (BM25) trước RRF
  vector_candidates: number      // Số chunk từ vector DB trước RRF
  rrf_candidates: number         // Sau RRF
}
```

**Ví dụ Response:**

```json
{
  "query_id": "q-7f3a2b91-4c1e-4d8f-b2a3-9e0f1c2d3e4f",
  "query": "tìm chỗ chill chill yên tĩnh gần biển cho 2 người",
  "total_found": 47,
  "returned": 10,
  "page": 0,
  "latency_ms": 312,
  "parsed_intent": {
    "original_query": "tìm chỗ chill chill yên tĩnh gần biển cho 2 người",
    "normalized_query": "tìm chỗ chill chill yên tĩnh gần biển cho 2 người",
    "hard_filters": {},
    "keyword_expansion": ["yên tĩnh", "quiet", "peaceful", "biển", "beachfront"],
    "intent_type": "hotel_search",
    "confidence": 0.87,
    "parsed_by": "llm"
  },
  "results": [
    {
      "hotel_id": 542,
      "name": "DoubleTree by Hilton Hotel & Suites Houston by the Galleria",
      "accommodation_type": "Khách sạn",
      "address": "5353 Westheimer Road, Westchase, Houston (TX), Hoa Kỳ",
      "city": "Houston (TX)",
      "latitude": 29.73919677734375,
      "longitude": -95.46896362304688,
      "star_rating": 3.0,
      "review_score": 7.6,
      "review_count": 1804,
      "is_luxury": false,
      "price_from": 1500000,
      "description": "Thêm an tâm với Hilton CleanStay khi quý khách đặt chỗ nghỉ ở đây...",
      "suitable_for": ["Khách đi công tác", "Cặp đôi", "Khách du lịch một mình"],
      "amenities_top": ["Bể bơi ngoài trời", "Phòng tập thể dục", "Nhà hàng", "Dịch vụ phòng"],
      "thumbnail_url": "https://pix8.agoda.net/hotelImages/542/0/e0c78afeef94c6dc7e060cb5d0fc554e.jpg",
      "image_count": 39,
      "ranking": {
        "final_score": 0.834,
        "rank": 1,
        "relevance_score": 0.912
      },
      "nearby_places": [
        { "name": "A.D. Players", "type": "Nhà hát", "distance_km": 0.28 }
      ],
      "source_url": "https://www.agoda.com/..."
    }
  ]
}
```

---

## 2. CONTEXT API

**Endpoint:** `POST /api/v1/context`

**Mục đích:** Với một khách sạn cụ thể đã được recommend, trả về **Context Package**
(evidence/chunks đã chọn lọc, tổng hợp và nén nếu cần, kèm citation) để DA09 dùng
sinh câu trả lời tự nhiên. DA10 = Retrieve, Ground, Provide Context.

---

### 2.1 Request Schema

```typescript
interface ContextRequest {

  // ── Bắt buộc ──────────────────────────────────────────────────────────────
  hotel_id: number
  // ID của khách sạn (hotels.id), lấy từ HotelCard.hotel_id trong SearchAPI

  query: string
  // Query gốc của người dùng — dùng để chọn chunk liên quan và rerank

  // ── Liên kết với SearchAPI (khuyến nghị) ──────────────────────────────────
  query_id?: string
  // UUID từ SearchResponse.query_id — dùng để cache/trace, tránh parse lại intent

  // ── Điều chỉnh nội dung context ───────────────────────────────────────────
  options?: {
    max_context_tokens?: number
    // Giới hạn token của context_text trả về, default: 1500

    include_chunks?: boolean
    // Nếu false → chỉ trả context_text (concatenated view), bỏ qua chunks[] chi tiết
    // Default: true — chunks[] là core của Context Package

    include_token_info?: boolean
    // Nếu true → trả thêm token_info (đếm token từng phần)
    // Default: false

    focus_aspects?: string[]
    // Hướng dẫn hệ thống ưu tiên aspect nào khi chọn chunk
    // Ví dụ: ["vị trí", "tiện nghi", "đánh giá"]
  }
}
```

**Ví dụ Request:**

```json
{
  "hotel_id": 542,
  "query": "tìm chỗ chill chill yên tĩnh gần biển cho 2 người",
  "query_id": "q-7f3a2b91-4c1e-4d8f-b2a3-9e0f1c2d3e4f",
  "options": {
    "max_context_tokens": 1500,
    "include_chunks": true,
    "include_token_info": true,
    "focus_aspects": ["không gian", "tiện nghi", "đánh giá"]
  }
}
```

---

### 2.2 Response Schema

```typescript
interface ContextResponse {

  // ── Định danh ─────────────────────────────────────────────────────────────
  hotel_id: number             // hotels.id
  hotel_name: string           // hotels.name
  query_id: string

  // ── PHẦN CHÍNH: Context Package ───────────────────────────────────────────
  context_text: string
  // Các chunks đã chọn lọc và nén, giữ text gốc, dùng làm evidence input cho DA09.
  // Không phải prose do LLM synthesis — chỉ concatenation/compression của top-K chunk đã rerank.

  // ── Chunks đã retrieve (core của Context Package) ───────────────────────────
  chunks: RetrievedChunk[]
  // Luôn có trong response. Rỗng khi options.include_chunks = false; đầy đủ khi true (default).

  // ── Citations — trích dẫn nguồn từng chunk trong Context Package ──────────
  citations: Citation[]

  // ── Metadata object — dữ liệu có cấu trúc đi kèm ─────────────────────────
  metadata: HotelMetadata

  // ── Token info (chỉ có khi include_token_info = true) ─────────────────────
  token_info?: TokenInfo

  latency_ms: number
}


// ─────────────────────────────────────────────────────────────────────────────
// Citation — trích dẫn nguồn từng đoạn trong context_text
// ─────────────────────────────────────────────────────────────────────────────
interface Citation {
  citation_id: string          // "cit-001", "cit-002" ...

  chunk_id: string             // ID của chunk trong bảng text_chunks
  source_type: "hotel_description" | "room_info" | "amenity" |
               "nearby" | "activity"
  // Map từ bảng nguồn:
  //   hotel_description  → hotels.description
  //   room_info          → rooms (name, room_amenities, bed_type, room_view)
  //   amenity            → hotels.amenities
  //   nearby             → nearby_places
  //   activity           → activities

  text_snippet: string
  // Đoạn text gốc của chunk — để hiển thị UI tooltip

  relevance_score: number      // Score reranker model cho chunk này với query (0.0–1.0)

  metadata: {
    source_table: "hotels" | "rooms" | "nearby_places" | "activities"
    source_column?: string     // Tên cột gốc: "description", "amenities", "name"...
    record_id?: number         // PK của record gốc (vd rooms.id, nearby_places.id)
  }
}


// ─────────────────────────────────────────────────────────────────────────────
// HotelMetadata — toàn bộ dữ liệu có cấu trúc của khách sạn
// (CHỈ chứa field có trong bảng PostgreSQL: hotels, rooms, nearby_places, activities)
// ─────────────────────────────────────────────────────────────────────────────
interface HotelMetadata {

  // ── Thông tin cơ bản (bảng hotels) ────────────────────────────────────────
  hotel_id: number             // hotels.id
  name: string                 // hotels.name
  accommodation_type: string   // hotels.accommodation_type
  star_rating: number          // hotels.star_rating
  is_luxury: boolean           // hotels.is_luxury

  // ── Vị trí (bảng hotels) ──────────────────────────────────────────────────
  address: string              // hotels.address
  city: string                 // hotels.city
  latitude: number             // hotels.latitude
  longitude: number            // hotels.longitude

  // ── Review tổng hợp (bảng hotels) ─────────────────────────────────────────
  review_score: number         // hotels.review_score
  review_count: number         // hotels.review_count
  reviews_detail: object       // hotels.reviews_detail (JSONB) — trả raw cho client tự parse

  // ── Mô tả & tiện nghi (bảng hotels) ───────────────────────────────────────
  description: string          // hotels.description (full text)
  amenities: string[]          // hotels.amenities (TEXT[])
  suitable_for: string[]       // hotels.suitable_for (TEXT[])

  // ── Chính sách (bảng hotels) ──────────────────────────────────────────────
  policy_notes: string[]       // hotels.policyNotes (TEXT[])
  useful_info: object          // hotels.useful_info (JSONB) — phí dịch vụ, etc.

  // ── Giá (tính từ bảng rooms) ──────────────────────────────────────────────
  price_from: number           // MIN(rooms.price) WHERE rooms.hotel_id = hotels.id

  // ── Danh sách phòng (bảng rooms) ──────────────────────────────────────────
  rooms: {
    id: number                 // rooms.id
    room_type_id: number       // rooms.room_type_id
    name: string               // rooms.name
    price: number              // rooms.price
    room_size: string          // rooms.room_size, ví dụ "38 m²"
    max_occupancy: number      // rooms.max_occupancy
    bed_type: string           // rooms.bed_type
    room_view: string | null   // rooms.room_view
    room_amenities: string[]   // rooms.room_amenities (TEXT[])
    images: string[]           // rooms.images (TEXT[])
    review_score: number       // rooms.review_score
  }[]

  // ── Địa điểm lân cận (bảng nearby_places) ─────────────────────────────────
  nearby_places: {
    id: number                 // nearby_places.id
    name: string               // nearby_places.name
    type: string               // nearby_places.type
    distance_km: number        // nearby_places.distance_km
  }[]

  // ── Hoạt động giải trí (bảng activities) ──────────────────────────────────
  activities: {
    id: number                 // activities.id
    title: string              // activities.title
    description: string        // activities.description
    price_amount: number       // activities.price_amount
    review_score: number       // activities.review_score
  }[]

  // ── Ảnh (bảng hotels) ─────────────────────────────────────────────────────
  images: string[]             // hotels.images (TEXT[])

  // ── Source (bảng hotels) ──────────────────────────────────────────────────
  source_url: string           // hotels.source_url
}


// ─────────────────────────────────────────────────────────────────────────────
// RetrievedChunk — chunk gốc từ vector index (core của Context Package)
// ─────────────────────────────────────────────────────────────────────────────
interface RetrievedChunk {
  chunk_id: string             // text_chunks.id
  text: string                 // Nội dung chunk (text_chunks.text hoặc tương đương)
  source_type: string          // Giống Citation.source_type

  scores: {
    bm25_rank?: number         // Thứ hạng trong OpenSearch BM25 (null nếu không có)
    vector_rank?: number       // Thứ hạng trong vector DB (null nếu không có)
    rrf_score: number          // Score sau RRF fusion
    reranker_score: number     // Score sau reranker model (final)
  }

  payload: {
    hotel_id: number           // Reference đến hotels.id
    source_table: string       // "hotels" | "rooms" | "nearby_places" | "activities"
    source_column?: string     // Cột gốc trong bảng
    record_id?: number         // PK của record gốc
    lang?: string              // "vi", "en"
  }
}


// ─────────────────────────────────────────────────────────────────────────────
// TokenInfo — thông tin token (chỉ có khi include_token_info = true)
// ─────────────────────────────────────────────────────────────────────────────
interface TokenInfo {
  context_text_tokens: number
  metadata_tokens: number
  total_tokens: number
  model_used_for_count: string // Tokenizer dùng để đếm
}
```

**Ví dụ Response:**

```json
{
  "hotel_id": 542,
  "hotel_name": "DoubleTree by Hilton Hotel & Suites Houston by the Galleria",
  "query_id": "q-7f3a2b91-4c1e-4d8f-b2a3-9e0f1c2d3e4f",
  "context_text": "Nằm ở vị trí trung tâm tại Westchase của Houston (TX)...\n---\nBể bơi ngoài trời, Phòng tập thể dục, Nhà hàng...\n---\nĐiểm đánh giá tổng 7.6/10 dựa trên 1804 đánh giá.",
  "chunks": [
    {
      "chunk_id": "chunk-542-desc-001",
      "text": "Nằm ở vị trí trung tâm tại Westchase của Houston (TX)...",
      "source_type": "hotel_description",
      "scores": {
        "bm25_rank": 3,
        "vector_rank": 1,
        "rrf_score": 0.82,
        "reranker_score": 0.91
      },
      "payload": {
        "hotel_id": 542,
        "source_table": "hotels",
        "source_column": "description",
        "lang": "vi"
      }
    }
  ],
  "citations": [
    {
      "citation_id": "cit-001",
      "chunk_id": "chunk-542-desc-001",
      "source_type": "hotel_description",
      "text_snippet": "Nằm ở vị trí trung tâm tại Westchase của Houston (TX)...",
      "relevance_score": 0.91,
      "metadata": {
        "source_table": "hotels",
        "source_column": "description"
      }
    }
  ],
  "metadata": {
    "hotel_id": 542,
    "name": "DoubleTree by Hilton Hotel & Suites Houston by the Galleria",
    "accommodation_type": "Khách sạn",
    "star_rating": 3.0,
    "is_luxury": false,
    "address": "5353 Westheimer Road, Westchase, Houston (TX), Hoa Kỳ",
    "city": "Houston (TX)",
    "latitude": 29.73919677734375,
    "longitude": -95.46896362304688,
    "review_score": 7.6,
    "review_count": 1804,
    "reviews_detail": { "grades": [], "tags": [], "demographics": [] },
    "description": "Thêm an tâm với Hilton CleanStay...",
    "amenities": ["Bàn tiếp tân 24 giờ", "Bể bơi ngoài trời", "..."],
    "suitable_for": ["Khách đi công tác", "Cặp đôi"],
    "policy_notes": ["Trẻ em từ 0-3 tuổi ở miễn phí..."],
    "useful_info": { "Phí Wifi/Internet hàng ngày": "9.95 USD" },
    "price_from": 1500000,
    "rooms": [],
    "nearby_places": [],
    "activities": [],
    "images": ["https://..."],
    "source_url": "https://www.agoda.com/..."
  },
  "token_info": {
    "context_text_tokens": 187,
    "metadata_tokens": 1240,
    "total_tokens": 1427,
    "model_used_for_count": "cl100k_base"
  }
}
```

---

## 3. Error Schema (dùng chung cho cả 2 API)

```typescript
interface ErrorResponse {
  error: {
    code: string
    // "INVALID_REQUEST"    — Request không đúng schema
    // "HOTEL_NOT_FOUND"    — hotel_id không tồn tại trong bảng hotels
    // "NO_RESULTS"         — Filter quá chặt, không có KS nào thoả
    // "INTENT_PARSE_FAIL"  — LLM model và rule-based đều fail
    // "RETRIEVAL_TIMEOUT"  — Pipeline vượt SLO 500ms
    // "INTERNAL_ERROR"     — Lỗi không xác định

    message: string          // Mô tả lỗi cho developer
    user_message?: string    // Mô tả thân thiện để hiển thị cho người dùng (tiếng Việt)
    query_id?: string        // Nếu đã sinh được query_id trước khi lỗi
    details?: object         // Chi tiết bổ sung
  }
}
```

---

## 4. Mapping Field API → Bảng PostgreSQL


| Field trong API                                                      | Bảng / Cột nguồn                                                                      |
| -------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| `hotel_id`, `name`, `accommodation_type`, `star_rating`, `is_luxury` | `hotels`                                                                              |
| `address`, `city`, `latitude`, `longitude`                           | `hotels`                                                                              |
| `review_score`, `review_count`, `reviews_detail`                     | `hotels`                                                                              |
| `description`, `amenities`, `suitable_for`                           | `hotels`                                                                              |
| `policy_notes`, `useful_info`, `images`, `source_url`                | `hotels`                                                                              |
| `price_from`                                                         | `MIN(rooms.price)` GROUP BY hotel_id                                                  |
| `rooms[]`                                                            | `rooms` (toàn bộ cột)                                                                 |
| `nearby_places[]`                                                    | `nearby_places` (toàn bộ cột)                                                         |
| `activities[]`                                                       | `activities` (toàn bộ cột)                                                            |
| `chunks[].chunk_id`, `text`, `payload`                               | `text_chunks` (bảng vector DB sẽ thêm)                                                |
| `context_text`                                                       | **Sinh bởi pipeline** (RRF + rerank + concatenation/compression, không LLM synthesis) |
| `chunks[]`                                                           | **Sinh bởi pipeline** (RRF + rerank, text gốc từ `text_chunks`)                       |
| `citations[]`                                                        | **Sinh bởi Chunking pipeline** (metadata payload của chunk)                           |
| `ranking.relevance_score`                                            | **Sinh bởi reranker model**                                                           |
| `parsed_intent`                                                      | **Sinh bởi LLM model** (intent parsing)                                               |


