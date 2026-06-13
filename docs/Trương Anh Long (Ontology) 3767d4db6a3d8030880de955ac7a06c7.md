# Trương Anh Long (Ontology)

![ontology_architecture_diagram.png](ontology_architecture_diagram.png)

```markdown
# DA10 — Knowledge Engineering
## Hướng dẫn triển khai chi tiết End-to-End (bản hoàn chỉnh)

> **Owner:** Trương Anh Long — vai trò **Knowledge Engineering** trong team DA10.
> **Mục tiêu tài liệu:** Một bản duy nhất, đủ chi tiết để bạn làm từ đầu đến cuối qua **4 sprint KE** mà không phải sửa lại. Mỗi đầu việc có: *mục đích → đầu vào → các bước → công nghệ → đầu ra → tiêu chí hoàn thành → cạm bẫy*, kèm rõ **cái gì bạn sở hữu / cái gì bạn bàn giao / cái gì bạn nhận từ người khác**.

## Tổng quan luồng làm việc (từ đầu đến cuối)

![Luồng làm việc Knowledge Engineering DA10 — từ đầu vào DA09, qua 4 sprint KE, bàn giao cho team, đến vòng đánh giá golden set](ontology_architecture_diagram.png)

> Sơ đồ trên tóm tắt toàn bộ tài liệu này: **đầu vào từ DA09** → các Sprint KE (Foundation → Enrichment → Knowledge Object → Evaluation) → **bàn giao** cho từng thành viên team → **vòng đánh giá** bằng golden set bao quanh tất cả. Đọc sơ đồ trước để nắm bức tranh tổng thể, rồi theo phần thân để đi vào chi tiết từng Task.

---

## ⚙ CẬP NHẬT THỰC TẾ (sau Sprint 1) — đọc trước khi theo phần thân

> Bản thân hướng dẫn dưới đây giữ NGUYÊN làm tham chiếu thiết kế. Nhưng khi thực thi Sprint 1 trên
> **51 hotel Agoda thật** (+ một lượt phản biện theo chuẩn search thực tế), một số quyết định đã được
> điều chỉnh cho đúng/scale hơn. **Khi làm theo tài liệu này, ưu tiên các điểm cập nhật dưới đây**
> ở những chỗ mâu thuẫn. Chi tiết đầy đủ: `docs/reports/ontology/sprint1/SPRINT1_REPORT.md` (mục 4).

| Chỗ trong hướng dẫn gốc | Đã điều chỉnh thành | Lý do |
|---|---|---|
| 1 file `concepts.yaml` gộp (Task 1.2) | **Tách theo facet**: `ontology/core/{object_type,amenity,location,setting,price_tier,purpose,style,aspect}.yaml` + `_meta.yaml` | 1 file vỡ khi lên 500–1000 concept |
| `labels` chứa lẫn synonym | Tách **`label`** (nhãn đại diện) khỏi **`surface_forms`** (cách gõ) | bản gốc trộn ontology với từ điển đồng nghĩa |
| (không có) | Thêm **`fact_type: hard\|soft`** trên mỗi concept | phân biệt lọc cứng vs tăng điểm |
| (không có) | Mô hình **Core vs Candidate** (`ontology/candidate/candidate_queue.yaml`) | kiểm soát ontology phình loạn |
| (mỏng) | Thêm hẳn **Location ontology** (25 địa danh + landmark) trong `location.yaml` | 90% query du lịch theo địa danh |
| star/giá/khoảng cách như concept | Để ở **`range_filters`** (metadata_schema), KHÔNG làm concept | đó là filter dạng khoảng, không phải khái niệm |
| synonym 1 form → 1 concept (Task 1.6) | 1 form → **LIST concept** | "lãng mạn" vừa purpose vừa style — giữ cả hai |
| metadata field `near_<landmark>` | Mô hình **`nearby_places[]` (category + distance)** + quan hệ `near` trỏ `LMK_*` | `near_vinwonders` là anti-pattern, không scale |
| file đầu ra ở `data/output/` hay `knowledge-engineering/output/` | **`docs/reports/ontology/sprint1/`** (code ở `knowledge_engineering/`, config ở `ontology/`) | tách báo cáo khỏi code; data/ là của ingestion |

> **Lớp A (tự sinh từ data):** quan hệ `near`, synonym_dictionary, domain stats — đều có script
> regenerate (xem SPRINT1_REPORT mục 6), chạy lại khi corpus đổi thay vì sửa tay.
>
> **Chưa xong Sprint 1 (chờ golden set DA09):** Task 1.1 Bước 2; Task 1.7 query_expansion (21 luật ở
> trạng thái `unverified`). Không đánh dấu "đã kiểm" khi chưa có golden set.

---

## Quy ước đọc

Vì DA10 là việc nhóm, mỗi phần được gắn nhãn ranh giới:

- **[BẠN SỞ HỮU]** — bạn tự xây và chịu trách nhiệm.
- **[BÀN GIAO → X]** — bạn tạo ra (dữ liệu/contract), thành viên X tiêu thụ.
- **[NHẬN ← X]** — đầu vào bạn nhận từ thành viên X.
- **[MODULE KHÁC: X]** — của người khác, đưa vào đây chỉ để bạn hiểu bức tranh.

Thứ tự đề xuất: đọc **Phần 0** (bối cảnh) → **Phần 1–2** (môi trường + interface) → làm theo **Sprint 1 → 4**. Mọi code là **mã minh họa**, hiểu ý trước, tối ưu sau.

---

## Mục lục

- [Phần 0 — Bối cảnh & vai trò](#phần-0--bối-cảnh--vai-trò)
- [Phần 1 — Công nghệ & môi trường](#phần-1--công-nghệ--môi-trường)
- [Phần 2 — Interface với team (contracts)](#phần-2--interface-với-team-contracts)
- [SPRINT 1 — Semantic Foundation](#sprint-1--semantic-foundation)
- [SPRINT 2 — Semantic Enrichment](#sprint-2--semantic-enrichment)
- [SPRINT 3 — Knowledge Object Generation](#sprint-3--knowledge-object-generation)
- [SPRINT 4 — Evaluation & Feedback](#sprint-4--evaluation--feedback)
- [Phần cuối — Timeline, Deliverables, Quickstart, Checklist](#phần-cuối--timeline-deliverables-quickstart-checklist)

---

# Phần 0 — Bối cảnh & vai trò

## 0.1 DA10 trong hệ thống

```text
DA09  (Trí tuệ)   = hiểu người dùng, tìm kiếm, gợi ý, sinh câu trả lời
   ↑ gọi API
DA10  (Tri thức)  = chuẩn hóa dữ liệu, làm giàu ngữ nghĩa, truy xuất
   ↑ dùng
Nguồn dữ liệu     = Hotel, Resort, Villa, Review, FAQ, ...
```

**Knowledge Engineering** là lớp tạo "ý nghĩa" cho dữ liệu. Chất lượng của nó là **trần chất lượng** của cả DA09: tag sai → gợi ý sai; thiếu khái niệm → query không tìm thấy gì.

## 0.2 Vị trí của BẠN trong team (đọc kỹ phần này)

Team 7 người, bạn là **Knowledge Engineering** (không có pair/backup). Hai điều định hình toàn bộ cách làm:

**(a) Mock-data-first.** DA09 cấp **đúng 4 đầu vào** (hạn cuối Tuần 1 của Sprint team):
`data_schema.json`, `metadata_schema.yaml`, `api_contract.yaml`, `golden dataset (30–50 query có nhãn)`.
Trước khi có dữ liệu thật, **bạn tự sinh mock metadata từ schema** để phát triển/test. **Real data (vd file Agoda) chỉ vào ở Sprint cuối.**

**(b) Ranh giới module.** Nhiều thứ trong thiết kế sâu chúng ta bàn *không* phải bạn code — bạn **cấp contract/dữ liệu**, người khác tiêu thụ:

| Việc | Ai sở hữu | Quan hệ với bạn |
|---|---|---|
| Concept / ontology / taxonomy / metadata schema | **Bạn** | Bạn sở hữu |
| Map nội dung → concept (`ontology_mapper`) | **Bạn** | Bạn sở hữu |
| Metadata pipeline, knowledge_objects | **Bạn** | Bạn sở hữu |
| Hotel semantic profile (từ review) | **Bạn** | Bạn sở hữu, **bàn giao →** Retrieval |
| Synonym dict + query expansion *rules* | **Bạn tạo** | **Bàn giao →** Anh Tài (áp dụng lúc query) |
| Chunking + Embedding (chọn bge-m3/PhoBERT, contextual) | Khánh Duy | **Bàn giao →** Khánh Duy (object + chunking_strategy + logic prefix); **Nhận ←** embedding service |
| Hybrid search + RRF + re-rank + đo metric | Anh Tài | **Bàn giao →** vocabulary/profile; Anh Tài đo Recall/MRR/NDCG |
| OpenSearch + Qdrant + index + SLO | Lê Hoàng Đạt | **Bàn giao →** schema để index |
| Cleaning / dedup / validation dữ liệu | Đỗ Minh Hiếu | **Nhận ←** dữ liệu sạch |
| API + Evaluation + gán nhãn golden set | Vũ Đức Kiên | Bạn **đồng** gán nhãn golden set với Kiên |
| Frontend demo | Nguyễn Duy Hiếu | — |

**Chỉ số mục tiêu của cả pipeline** (Anh Tài/Kiên đo, bạn góp phần lớn vì lớp ngữ nghĩa quyết định relevance): **Recall@10 ≥ 0.8, MRR ≥ 0.7, NDCG ≥ 0.75, p95 latency < 500ms**, so với **BM25-only baseline**.

> **Cần làm rõ với team:** `metadata_schema.yaml` vừa nằm trong "DA09 cấp", vừa là contract bạn chốt. Thống nhất ngay: **DA09 cấp bản gốc data-level, bạn mở rộng phần KE-specific (ontology/taxonomy/tag), đồng version** — kẻo hai bên định nghĩa lệch nhau.

## 0.3 Tư duy quan trọng nhất: pipeline → vòng lặp đánh giá

Đừng làm tuyến tính rồi đánh giá ở cuối. *Coverage* (bao nhiêu doc được gắn tag) **không** đo đúng/sai. Dùng **golden set** (DA09 cấp, bạn + Kiên gán nhãn bổ sung) làm thước đo: mỗi lần sửa ontology/tag đều chạy lại, đo bằng con số.

```text
        ┌──────────────────────────────────────────┐
        ▼                                            │
Sửa concept/tag → Chạy golden set → Đo chỉ số → Tốt hơn? ──Không──┐
        ▲                                                          │
        └──────────────────── Có: giữ lại ◄─────────────────────────┘
```

## 0.4 Mô hình tư duy: một vốn từ vựng, nhiều góc nhìn

```text
            concepts.yaml   (NGUỒN SỰ THẬT DUY NHẤT — các "nguyên tử" ý nghĩa)
            /        |          |             \
       ontology    facets      synonym_dict    query_expansion
       (mô tả +    (tổ chức    (từ ngữ →       (concept →
        quan hệ)   theo chiều)  concept)        concept)
```

Sửa một nhãn ở `concepts.yaml` → mọi file dẫn xuất cập nhật theo. **Sinh tự động** các file dẫn xuất thay vì viết tay rồi để lệch nhau.

## 0.5 BA THỨ TÁCH BIỆT (khái niệm cốt lõi nhất — đừng nhầm)

Đây là điểm dễ sai nhất và quyết định cả thiết kế của bạn:

```text
1) Ontology / Concept layer   = bộ khái niệm CHUNG toàn hệ thống. ỔN ĐỊNH.
   → Trả lời: "hệ thống hiểu những khái niệm gì?"   (concepts.yaml, ontology.yaml, facets.yaml)

2) Hotel Semantic Profile     = SCORE RIÊNG của từng khách sạn TRÊN ontology chung. ĐỘNG.
   → Trả lời: "khách sạn này mạnh/yếu ở khái niệm nào?"   (vd Vinpearl STYLE_QUIET=0.91)

3) Review Evidence            = bằng chứng từ TỪNG review (span, sentiment, confidence).
   → Nguồn nuôi cho profile.
```

**Quy tắc vàng:**

```text
Review mới
  → clean / normalize
  → ABSA + map vào concept CÓ SẴN
  → lưu review-level evidence
  → AGGREGATE lên hotel semantic profile     (KHÔNG đụng tới ontology)
  → keyword lạ lặp nhiều → candidate queue
  → HUMAN duyệt → mới thêm vào concepts.yaml
  → chạy lại golden set → tốt hơn mới merge
```

> **Sai lầm phổ biến:** "review nói gì → thêm concept đó". Sau 6 tháng bạn sẽ có `QUIET / VERY_QUIET / PEACEFUL / CHILL / HEALING / YEN_TINH...` — hàng nghìn concept trùng nghĩa, retrieval loạn. Đúng phải là: review **map vào concept có sẵn**; ontology chỉ đổi qua human + golden set.

## 0.6 Luồng end-to-end (phần của bạn + interface)

```text
[Nguồn thô]            ── Data Quality (Đỗ Minh Hiếu) làm sạch ──►  [Dữ liệu sạch]  ──► BẠN
                                                                                      │
SPRINT 1  Nền tảng ngữ nghĩa         concepts/ontology/facets/synonym/expansion/metadata_schema
SPRINT 2  Làm giàu                   ontology_mapper (tag) + metadata_pipeline + review→profile
SPRINT 3  Knowledge object           knowledge_objects.json + chunking_strategy + context-prefix
                                          │ bàn giao
                ┌─────────────────────────┼──────────────────────────┐
                ▼                          ▼                          ▼
   Khánh Duy: chunk+embed     Anh Tài: query rewrite/expand,    Đạt: index (ES+Qdrant)
                              hybrid (BM25+vector)+RRF+rerank
                                          │ dùng profile + vocabulary của BẠN
                                          ▼
                              Search Results + Context  ──► DA09

         ⟲  Đánh giá (golden set) bao quanh tất cả — SPRINT 4 + xuyên suốt
```

## 0.7 Thuật ngữ

| Thuật ngữ | Nghĩa đơn giản |
|---|---|
| **Ontology / Concept layer** | Bộ khái niệm chung, có ID, ổn định |
| **Concept** | Đơn vị ý nghĩa trung tính (vd `STYLE_QUIET`) |
| **Facet** | Một *chiều* phân loại độc lập (vị trí, giá, mục đích...) |
| **Hotel Semantic Profile** | Điểm số riêng của từng khách sạn trên các concept |
| **Review Evidence** | Bằng chứng (câu trích) từ một review cho một concept |
| **Surface form** | Từ ngữ bề mặt người dùng gõ ("hồ bơi", "bể bơi", "pool") |
| **Source-tag mapping** | Map tag/amenity của nguồn crawl → concept của bạn |
| **Embedding** | Vector số biểu diễn ý nghĩa văn bản |
| **Chunk** | Đoạn nhỏ cắt từ tài liệu dài |
| **Contextual retrieval** | Dán 1 câu ngữ cảnh vào chunk trước khi embed |
| **Payload** | Metadata kèm vector, dùng để **lọc** |
| **Filter vs Score** | Filter = điều kiện cứng (loại/giữ); Score = điểm mềm để xếp hạng |
| **BM25 / Hybrid / RRF** | Xếp hạng từ khóa / kết hợp vector+từ khóa / cách trộn 2 bảng kết quả |
| **Confidence / Provenance** | Độ tin cậy của nhãn / nguồn gốc (tầng nào gắn) |
| **ABSA** | Cảm xúc theo *từng khía cạnh* của review |
| **Candidate queue** | Hàng đợi concept ứng viên chờ người duyệt |
| **Wilson/Bayesian smoothing** | Cách làm trơn score khi ít bằng chứng để không overconfident |
| **Golden set** | Bộ test chuẩn: query + tài liệu đúng (DA09 cấp) |
| **Recall@10 / MRR / NDCG** | % bắt đúng trong top 10 / vị trí kết quả đúng đầu / chất lượng thứ tự |

---

# Phần 1 — Công nghệ & môi trường

## 1.1 Tech stack (đánh dấu cái nào BẠN dùng)

| Hạng mục | Công nghệ | Ai dùng |
|---|---|---|
| Ngôn ngữ | **Python 3.10+** | Tất cả |
| Tách từ / chuẩn hóa tiếng Việt | **underthesea** + **unicodedata** | **Bạn** (sinh synonym + chuẩn hóa tag); chia sẻ với Anh Tài/Data Quality |
| Cấu hình | **YAML** (`pyyaml`) | **Bạn** |
| Kiểm tra schema | **pydantic** | **Bạn** |
| Embedding (model) | **bge-m3** / PhoBERT / multilingual-e5 | **Khánh Duy benchmark & chọn**; bạn *dùng* service để tính anchor |
| Tính cosine | **numpy** | **Bạn** (cho embedding tagger) |
| LLM (tag khó + ABSA) | **Claude API** (`anthropic`) | **Bạn** |
| Vector DB / Index | **Qdrant + OpenSearch 2.x** | Lê Hoàng Đạt |
| Hybrid/RRF/rerank | code riêng | Anh Tài |
| Đo lường | **ranx** (Recall@k, MRR, NDCG) | Anh Tài / Kiên |
| Xử lý bảng | **pandas** | **Bạn** (domain analysis) |
| Versioning | **git** (+ DVC tùy chọn) | Tất cả |

> ⚠ Theo phản hồi mentor: **không mặc định OpenAI embedding** — Khánh Duy bắt buộc benchmark bge-m3/PhoBERT/e5 trên corpus tiếng Việt. Bạn chỉ cần *thống nhất* dùng model nào để dựng anchor (Sprint 2) cho nhất quán với search.

## 1.2 Cài đặt (phần của bạn)

```bash
python -m venv .venv && source .venv/bin/activate
pip install pyyaml pydantic pandas numpy
pip install underthesea            # chuẩn hóa tiếng Việt
pip install sentence-transformers  # dựng anchor (dùng model team chọn)
pip install anthropic              # Claude API cho tag khó + ABSA
export ANTHROPIC_API_KEY="..."     # để trong .env, KHÔNG commit
```

## 1.3 Thư mục (file của BẠN)

```text
knowledge-engineering/
├── config/
│   ├── concepts.yaml            # [BẠN] nguồn sự thật khái niệm
│   ├── facets.yaml              # [BẠN] taxonomy đa chiều (= taxonomy.yaml)
│   ├── ontology.yaml            # [BẠN] mô tả + quan hệ (KG nhẹ)
│   ├── synonym_dictionary.yaml  # [BẠN tạo → Anh Tài] surface → concept
│   ├── query_expansion.yaml     # [BẠN tạo → Anh Tài] concept → concept
│   ├── metadata_schema.yaml     # [BẠN] CONTRACT (đồng bộ với DA09)
│   ├── tagging_rules.yaml       # [BẠN] luật Tầng 1
│   ├── source_tag_map.yaml      # [BẠN] map tag nguồn crawl → concept
│   └── chunking_strategy.yaml   # [BẠN tạo → Khánh Duy] cách cắt chunk
├── src/
│   ├── normalize.py             # [BẠN] chuẩn hóa tiếng Việt
│   ├── build_synonym_index.py   # [BẠN] sinh synonym từ concepts
│   ├── anchors.py               # [BẠN] anchor vector (dùng model team)
│   ├── ontology_mapper.py       # [BẠN] tagger lai 3 tầng + fusion
│   ├── absa.py                  # [BẠN] aspect-based sentiment review
│   ├── profile_builder.py       # [BẠN] aggregate review → hotel profile
│   ├── metadata_pipeline.py     # [BẠN] map/validate/reconcile metadata
│   ├── build_objects.py         # [BẠN] tạo knowledge_objects.json
│   └── llm.py                   # [BẠN] bọc Claude API trả JSON
├── data/
│   ├── mock/                    # mock metadata tự sinh (Sprint 1-2)
│   ├── real/                    # dữ liệu thật (Sprint 3, vd Agoda)
│   └── output/
│       ├── domain_analysis.md
│       ├── knowledge_objects.json
│       ├── hotel_semantic_profiles.json
│       └── knowledge_report.md
└── README.md
```

---

# Phần 2 — Interface với team (contracts)

Đây là "mặt tiếp xúc" của bạn — nắm rõ để không ai làm lệch nhau.

**Bạn NHẬN:**
- **← Data Quality (Đỗ Minh Hiếu):** dữ liệu đã clean/dedup/validate.
- **← Khánh Duy:** embedding service (để dựng anchor + sau này embed chunk).
- **← DA09/Kiên:** `data_schema.json`, `metadata_schema.yaml` (base), `golden dataset`.

**Bạn BÀN GIAO:**
- **→ Khánh Duy:** `knowledge_objects.json` (có metadata) + `chunking_strategy.yaml` + hàm dựng `context_prefix`. Khánh Duy chunk + embed.
- **→ Anh Tài:** `synonym_dictionary.yaml` + `query_expansion.yaml` (để query_processor áp lúc query) + `hotel_semantic_profiles.json` (để ranking dùng làm điểm relevance).
- **→ Đạt:** `metadata_schema.yaml` để tạo index mapping; cấu trúc `payload`.
- **→ Kiên:** đồng gán nhãn golden set; báo cáo coverage.

**3 CONTRACT chốt cuối Sprint 1** (mentor yêu cầu — bạn liên quan trực tiếp cái thứ 2):
1. `data_schema.json` (Đỗ Minh Hiếu chủ trì)
2. `metadata_schema.yaml` (**bạn chủ trì**, đồng bộ DA09)
3. `api_contract.yaml` (Kiên chủ trì)

**Schema Change Protocol:** đổi schema giữa chừng → tạo GitHub Issue ngay → họp nhanh trong 24h → cập nhật cả 3 contract cùng lúc → tăng version (v1.1...). **Không ai tự ý sửa** mà không thông báo. Mọi file config của bạn cũng versioned.

---

# SPRINT 1 — Semantic Foundation

> **Mục tiêu:** Thiết kế toàn bộ nền tảng ngữ nghĩa **song ngữ Việt–Anh** + **đa chiều (faceted)**, chốt contract `metadata_schema.yaml`. **Làm trên mock data tự sinh.**
> **Khung thời gian team:** trùng **Sprint 1 (Tuần 1–2)** — contract chốt cuối Tuần 1.

## Task 1.1 — Domain Analysis · [BẠN SỞ HỮU]

**Mục đích:** Hiểu dữ liệu + đọc ngược từ query để biết người dùng lọc theo *chiều* nào → đó là facet.

**Đầu vào:** mock metadata (tự sinh từ `metadata_schema.yaml`) + golden queries + **file Agoda như "hình mẫu dữ liệu thật"** để biết các trường thực tế (`tags`, `amenities`, `suitable_for`, `nearby_places`, `reviews_detail`...).

**Các bước:**
1. Liệt kê ≥ 20 semantic concept hay gặp (`luxury, quiet, family, beachfront, spa, private pool, kids club...`).
2. Nhóm 30+ golden query theo chiều quan tâm (tiện ích / vị trí / nhóm khách / giá / phong cách) → ra danh sách facet ứng viên.
3. Ghi đặc thù tiếng Việt: không dấu, từ ghép ("hồ bơi"), từ mượn ("homestay", "view"), viết tắt ("ks").
4. Ghi **vốn từ vựng nguồn** (Agoda dùng "bể bơi", "Hướng Đại dương"...) để chuẩn bị `source_tag_map`.

**Đầu ra:** `domain_analysis.md`. **Done khi:** ≥ 30 query + ≥ 20 concept + danh sách facet + ghi chú vocabulary nguồn.

## Task 1.2 — Concept Registry · [BẠN SỞ HỮU]

**Mục đích:** Vốn từ vựng trung tính — **tách ý nghĩa khỏi ngôn ngữ**. ID trung tính (`STYLE_LUXURY`), tiếng Việt/Anh chỉ là *nhãn*.

```yaml
# config/concepts.yaml — NGUỒN SỰ THẬT DUY NHẤT
STYLE_QUIET:
  facet: style
  labels:
    vi: [yên tĩnh, tĩnh lặng, không ồn ào, im ắng, thanh bình]
    en: [quiet, peaceful, calm]
  description:
    vi: Không gian ít tiếng ồn, phù hợp nghỉ dưỡng
    en: Low-noise environment, good for relaxation
  related: [STYLE_RELAXING, SETTING_NATURE]

AMEN_BEACHFRONT:
  facet: amenity
  labels:
    vi: [sát biển, ven biển, gần biển, ngay bãi biển, view biển]
    en: [beachfront, by the beach, sea view, ocean view]
  description: {vi: Vị trí ngay sát bãi biển, en: Right on the beach}
  broader: SETTING_COASTAL
```

> **QUY TẮC QUAN TRỌNG — concept TRUNG TÍNH về cảm xúc.** KHÔNG đặt `STYLE_NOT_QUIET`, `ROOM_CLEAN`, `STAFF_FRIENDLY` (nhét tốt/xấu vào ID). Chỉ một concept trung tính (`STYLE_QUIET`, `ASPECT_CLEANLINESS`, `ASPECT_STAFF`), còn tốt/xấu để ở **trường `sentiment`**. Nếu nhét polarity vào ID, bạn sẽ nhân đôi số concept (`NOT_QUIET`, `NOT_CLEAN`...) — đúng cái explosion cần tránh.

**Done khi:** ≥ 30 concept đủ `facet + labels(vi/en) + description`; không có 2 ID trùng nghĩa.

## Task 1.3 — Vietnamese Normalization · [BẠN SỞ HỮU] (dùng chung)

**Mục đích:** Hàm `normalize()` áp cho **cả query lẫn nhãn** theo *cùng* quy trình. (Chia sẻ với Anh Tài/Data Quality — thống nhất một bản.)

```python
# src/normalize.py
import unicodedata
from underthesea import word_tokenize

def to_nfc(t): return unicodedata.normalize("NFC", t)

def strip_diacritics(t):                       # "gần biển" -> "gan bien"
    nfd = unicodedata.normalize("NFD", t)
    out = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return out.replace("đ","d").replace("Đ","D")

def segment(t): return word_tokenize(t, format="text")   # "hồ bơi" -> "hồ_bơi"

def normalize(t, fold=False):
    t = segment(to_nfc(t).lower().strip())
    return strip_diacritics(t) if fold else t
```

**Ba việc:** NFC (dấu tổ hợp vs dựng sẵn) → tách từ (từ ghép) → biến thể bỏ dấu. **Done khi:** `normalize("Resort Gần Biển")` và `normalize("resort gan bien", fold=True)` khớp được vào synonym dict.

## Task 1.4 — Taxonomy đa chiều (Faceted) · [BẠN SỞ HỮU] (= taxonomy.yaml)

**Mục đích:** Thay cây phẳng bằng nhiều **trục độc lập**. Một resort *đồng thời* là loại hình + vị trí + nhóm khách + tiện ích + giá + phong cách.

**4 nguyên tắc:** trực giao; cardinality rõ (một-giá-trị vs nhiều-giá-trị); phân cấp chỉ ở nơi cần (location sâu, amenity 2 tầng, purpose phẳng); value = concept_id (dùng chung vốn từ).

**Điểm ăn tiền:** mỗi facet khớp 1–1 với **slot của DA09** → query phân tích ra slot chuyển thẳng thành filter.

```yaml
# config/facets.yaml
facets:
  object_type: {cardinality: one, da09_slot: accommodation_type,
                values_tree: {accommodation: [hotel, resort, villa, homestay], content: [review, faq, guide]}}
  location:    {cardinality: one, da09_slot: destination,
                hierarchy: [country, region, province, district, area]}
  purpose:     {cardinality: many, da09_slot: audience,
                values: [family, romantic, business, solo, group, wellness]}
  amenity:     {cardinality: many,
                values_groups: {water: [private_pool, beachfront, sea_view],
                                family: [kids_club, family_room], wellness: [spa, gym, sauna]}}
  price_tier:  {cardinality: one, da09_slot: budget, values: [budget, mid, upscale, luxury]}
  style:       {cardinality: many, values: [quiet, lively, romantic, modern, eco]}
  aspect:      {cardinality: many, values: [room, staff, location, food, cleanliness, value]}  # cho ABSA
```

**Done khi:** mọi loại dữ liệu đặt được vào facet; mỗi query mẫu phân rã được thành *(filter facet + tập concept)*.

## Task 1.5 — Ontology (+ quan hệ / KG nhẹ) · [BẠN SỞ HỮU]

**Mục đích:** Thêm mô tả + **quan hệ** giữa concept để trả lời query "gần X" (đồ thị, không phải keyword).

```yaml
# config/ontology.yaml
concepts:
  AMEN_BEACHFRONT: {description_vi: Vị trí ngay sát bãi biển, broader: SETTING_COASTAL}
entities:
  VinWonders_NhaTrang: {type: landmark, located_in: NhaTrang}
relations:
  - {from: acc_vinpearl_nhatrang, rel: near, to: VinWonders_NhaTrang, distance_km: 0.65}
```

> **Mẹo từ data thật:** file Agoda đã có `nearby_places` kèm khoảng cách → bạn **chuẩn hóa thẳng** vào quan hệ `near` (VinWonders 0.65km...). Chỉ cần một bảng `near` đơn giản đã cải thiện mạnh nhóm "gần landmark".

**Done khi:** ≥ 30 concept có mô tả; có quan hệ `near`/`located_in` cho landmark chính.

## Task 1.6 — Synonym Dictionary · [BẠN tạo → Anh Tài]

**Mục đích:** Bản đồ **surface form (chuẩn hóa) → concept_id**. Sinh tự động từ `concepts.yaml`. Anh Tài dùng nó trong `query_processor` lúc query; bạn dùng nó ở Tầng 1 tagger.

```python
# src/build_synonym_index.py
import yaml
from normalize import normalize
def build(src="config/concepts.yaml", out="config/synonym_dictionary.yaml"):
    c = yaml.safe_load(open(src, encoding="utf-8")); idx = {}
    for cid, x in c.items():
        for lang in ("vi","en"):
            for lb in x.get("labels",{}).get(lang,[]):
                idx[normalize(lb)] = cid; idx[normalize(lb, fold=True)] = cid
    yaml.safe_dump(idx, open(out,"w",encoding="utf-8"), allow_unicode=True)
```

**Done khi:** ≥ 100 surface form (kể cả bỏ dấu).

## Task 1.7 — Query Expansion · [BẠN tạo → Anh Tài]

**Mục đích:** Mở rộng **concept → concept** để tăng Recall. Bạn tạo *rules*; Anh Tài *áp dụng* lúc query.

```yaml
# config/query_expansion.yaml
STYLE_LUXURY:   {expands_to: [AMEN_SPA, AMEN_PRIVATE_POOL, AMEN_SEA_VIEW]}
PURPOSE_FAMILY: {expands_to: [AMEN_KIDS_CLUB, ROOM_FAMILY]}
PURPOSE_ROMANTIC: {expands_to: [AMEN_SEA_VIEW, AMEN_PRIVATE_DINNER]}
```

> ⚠ Mở rộng nhiều quá → giảm precision. **Mỗi rule kiểm trên golden set**, không tăng thì bỏ. **Done khi:** ≥ 20 rule đã kiểm.

## Task 1.8 — Metadata Schema (CONTRACT) · [BẠN SỞ HỮU, đồng bộ DA09]

**Mục đích:** Schema chuẩn cho mọi knowledge object, dùng được để Filter / Retrieve / Generate Context. Validate bằng `pydantic`.

```yaml
# config/metadata_schema.yaml
knowledge_object:
  id: str; type: str; title: str; content: str; source: str
  metadata:
    object_type: str
    location: {country: str, province: str, district: str, area: str}
    purpose: [str]; amenity: [str]; price_tier: str; star_rating: int; style: [str]
  tags: [{concept: str, confidence: float, sources: [str]}]
review_extra:
  overall_sentiment: str
  aspects: [{aspect: str, sentiment: str, confidence: float, span: str}]
```

**Done khi:** validate được object mẫu; chốt chung với DA09 (version v1.0).

---

# SPRINT 2 — Semantic Enrichment

> **Mục tiêu:** Tự động gắn semantic info + xử lý review → hotel semantic profile. Nguyên tắc: **cascade** rẻ→đắt; **mọi nhãn có `confidence` + `source`**. **Làm trên mock data**; thiết kế sẵn cho data thật.
> **Khung thời gian team:** trùng **Sprint 2 (Tuần 3–4)** — walking skeleton chạy với mock; golden set gán nhãn xong cuối Tuần 1.

## Task 2.1 — Ontology Mapper: tagger lai 3 tầng · [BẠN SỞ HỮU]

```text
Văn bản → Tầng 1 Rules (synonym_dict, conf~0.95, xử lý phủ định)
        → Tầng 2 Embedding (cosine vs anchor concept; conf=f(sim))
        → Tầng 3 LLM (suy luận ngầm + phân xử; ràng buộc vocabulary; JSON)
        → Hợp nhất (1 tag/concept; nhiều tầng đồng thuận → +conf; ghi sources)
        → conf ≥ ngưỡng: nhận | conf < ngưỡng: hàng đợi review
```

```python
# src/ontology_mapper.py (rút gọn)
from normalize import normalize
from collections import defaultdict
import numpy as np

def tag_rules(text, syn, rules):
    norm = normalize(text); out=[]
    for s, cid in syn.items():
        if s in norm and not has_negation_near(norm, s, rules["negation_cues"]):
            out.append({"concept":cid,"confidence":0.95,"source":"rule","evidence":s})
    return out

def tag_embedding(text, anchors, model, th=0.55, done=set()):
    v = model.encode(text, normalize_embeddings=True); out=[]
    for cid, a in anchors.items():
        if cid in done: continue
        sim = float(np.dot(v,a))
        if sim>=th:
            conf = 0.5 + 0.5*(sim-th)/(1-th)
            out.append({"concept":cid,"confidence":round(conf,2),"source":"embedding","evidence":f"cos={sim:.2f}"})
    return out

def fuse(all_tags):
    by=defaultdict(list); [by[t["concept"]].append(t) for t in all_tags]; out=[]
    for cid, hits in by.items():
        srcs=sorted({h["source"] for h in hits}); conf=max(h["confidence"] for h in hits)
        if len(srcs)>=2: conf=min(1.0, conf+0.1)
        out.append({"concept":cid,"confidence":round(conf,2),"sources":srcs,
                    "evidence":[h["evidence"] for h in hits]})
    return out
```

LLM (Tầng 3) chỉ chạy cho ca khó/mâu thuẫn/confidence thấp, **chỉ chọn concept trong ALLOWED**, trả JSON. Anchor (`anchors.py`) dựng từ `description` song ngữ bằng model Khánh Duy chọn.

**Done khi:** chạy đủ 3 tầng + fuse ra tag có confidence + sources; xử lý đúng phủ định; ngưỡng embedding calibrate trên golden set.

## Task 2.2 — Source-tag Mapping (Layer 0) · [BẠN SỞ HỮU]

> **[BỔ SUNG]** Tận dụng data crawl giàu (như Agoda) làm đầu vào chất lượng cao cho tagger.

**Mục đích:** Data crawl đã có sẵn `tags`/`amenities`/`suitable_for`/`view_types`... nhưng theo **vocabulary của nguồn** ("Bể bơi", "Hướng Đại dương"). Map chúng → concept của bạn, **confidence cao, gần như miễn phí** → trở thành "Tầng 0" trước cả Tầng 1.

```yaml
# config/source_tag_map.yaml — map vocabulary nguồn → concept
agoda:
  "Bể bơi": AMEN_POOL
  "Bể bơi có tầm nhìn": AMEN_INFINITY_POOL
  "Bãi biển riêng": AMEN_PRIVATE_BEACH
  "Hướng Đại dương": AMEN_SEA_VIEW
  "Gia đình có trẻ nhỏ": PURPOSE_FAMILY
  "Cặp đôi": PURPOSE_ROMANTIC
```

> **Vì sao vẫn cần lớp của bạn dù crawl giàu:** crawl dùng "**bể bơi**", nhưng người dùng (nhất là miền Nam) gõ "**hồ bơi**"; nguồn khác (Booking/CMS) lại dùng từ khác. **Không gì trong crawl nối "bể bơi" ≡ "hồ bơi" ≡ "pool"** — đó chính là việc của concept layer + synonym. Crawl giàu *càng cần* lớp chuẩn hóa vì có nhiều vocabulary để hợp nhất.

**Done khi:** mỗi nguồn có bảng map; tag nguồn được chuyển thành concept với `source: "source_tag"`.

## Task 2.3 — Metadata Pipeline (map/validate/reconcile) · [BẠN SỞ HỮU]

> **[ĐỔI VAI so với bản gốc]** Với data crawl giàu, đây **không** còn là "trích xuất từ văn bản thô" mà là **map + validate + đối chiếu**.

**Các bước:**
1. **Map** trường crawl → schema của bạn (vd `area: "Hòn Tre"` → chuẩn hóa vào cây `location`; `accommodation_type: "Resort"` → `object_type`).
2. **Validate** theo `metadata_schema.yaml` (pydantic) — bắt trường thiếu/sai kiểu.
3. **Đối chiếu mâu thuẫn**: vd Agoda ghi `is_luxury: false` cho resort **5 sao + Gold Circle** → **đừng tin cờ nguồn mù**, tự suy `price_tier`/`style` theo logic của bạn.
4. **Bù trường thiếu** cho nguồn nghèo hơn (nguồn không có `nearby_places`, không có review tags...).

**Đầu ra:** `metadata_pipeline.py`. **Done khi:** trường chính đúng cho phần lớn doc; xử lý đúng vài ca mâu thuẫn.

## Task 2.4 — Review → Aspect Sentiment & Hotel Profile · [BẠN SỞ HỮU → bàn giao profile cho Anh Tài]

> **[BỔ SUNG LỚN]** Đây là phần review. Nhớ **BA THỨ TÁCH BIỆT** (Phần 0.5): review **không** sửa ontology; review sinh **evidence** → aggregate lên **hotel semantic profile**.

### (a) ABSA — concept TRUNG TÍNH + sentiment riêng

```python
# src/absa.py
from llm import claude_json
ABSA_SYSTEM = """Trích cảm xúc theo khía cạnh từ review du lịch tiếng Việt.
aspect CHỈ trong: [room, staff, location, food, cleanliness, value].
Mỗi khía cạnh được nhắc -> {aspect, sentiment: positive|negative|neutral|mixed, confidence, span}.
CHỈ trả JSON {"overall_sentiment": "...", "aspects": [...]}.
Ví dụ: "Phòng sạch nhưng tối hơi ồn" ->
{"overall_sentiment":"mixed","aspects":[
 {"aspect":"room","sentiment":"positive","span":"Phòng sạch"},
 {"aspect":"location","sentiment":"negative","span":"tối hơi ồn"}]}"""
def extract_absa(text): return claude_json(ABSA_SYSTEM, text)
```

> Khi map sang concept mô tả (style/purpose), vẫn **trung tính**: review "hơi ồn" → `{concept: STYLE_QUIET, sentiment: negative}`, **KHÔNG** `STYLE_NOT_QUIET`.

### (b) Hotel Semantic Profile — định nghĩa score rõ + làm trơn

> **[CHỈNH SỬA quan trọng]** Đừng cộng `+1` thô. **Định nghĩa score nhất quán + trọng số theo lượng bằng chứng** để concept ít review không bị overconfident.

```text
Với mỗi (hotel, concept):
  pos, neg = số evidence tích cực / tiêu cực (mỗi review tối đa 1 phiếu/concept; dedupe spam)
  raw = pos / (pos + neg)
  score = wilson_lower_bound(pos, pos+neg)      # làm trơn: ít dữ liệu -> score thấp hơn raw
  evidence_count = pos + neg
  (tùy chọn) decay theo thời gian: review cũ giảm trọng số
```

```json
// data/output/hotel_semantic_profiles.json
{
  "hotel_id": "acc_vinpearl_nhatrang",
  "semantic_profile": {
    "ASPECT_CLEANLINESS": {"score": 0.86, "pos": 300, "neg": 22, "evidence_count": 322},
    "STYLE_QUIET":        {"score": 0.40, "pos": 60,  "neg": 120, "evidence_count": 180},
    "PURPOSE_FAMILY":     {"score": 0.71, "pos": 80,  "neg": 8,   "evidence_count": 88}
  },
  "last_updated": "2026-06-03"
}
```

> **Score = gì?** Phân biệt rõ: concept **sự thật/tiện ích** (beachfront, có spa) → presence gần như chắc chắn, lấy từ **structured data** (Task 2.2/2.3), không phải đếm review. Concept **trải nghiệm** (quiet, romantic, chất lượng dịch vụ) → mới lấy từ **aggregate review**. Ghi rõ nguồn của từng score.

> **Tận dụng crawl:** file Agoda đã có `reviews_detail.tags` (mentioned + positive_pct) + `grades` + `rating_breakdown` — **seed/đối chiếu** profile từ đây cho nguồn có sẵn. ABSA per-review của bạn thêm phần crawl *không* có: **span dẫn chứng** (để DA09 giải thích), **concept ngoài 6 aspect** (style/purpose), và **đồng bộ nguồn không có aggregate**.

### (c) Luồng production xử lý review

```text
[Review mới] → 1.Validate(hotel_id, text, rating, source)
            → 2.Normalize
            → 3.Rule tagger (keyword rõ + phủ định)
            → 4.Embedding tagger (cách nói lạ)
            → 5.LLM/ABSA (review dài / mâu thuẫn / conf thấp; JSON; allowed vocab)
            → 6.Fuse (rule+embed+LLM; conf+source)
            → 7.Lưu review-level evidence (review_id, hotel_id, concept, sentiment, conf, span, source)
            → 8.Aggregate lên hotel_semantic_profile (score + smoothing + evidence_count)
            → 9.Keyword lạ lặp nhiều → candidate queue
            → 10.[Nếu ontology đổi] human duyệt → sửa concepts.yaml → generate lại synonym/expansion → chạy golden set → tốt hơn mới merge
```

**Incremental:** lần đầu xử lý toàn bộ review lịch sử → build profile; sau đó review mới cộng dồn; **định kỳ rebuild** chống sai lệch; **đổi ontology/prompt ABSA lớn → reprocess toàn bộ**.

### (d) Các lớp dữ liệu cần tách

```text
concepts.yaml                  (ontology config — ổn định)
reviews                        (raw: review_id, hotel_id, text, rating, source, created_at)
review_concept_evidence        (review_id, hotel_id, concept_id, sentiment, confidence, span, source)
hotel_semantic_profile         (hotel_id, concept_id, score, pos, neg, evidence_count, last_updated)
ontology_candidate_queue       (candidate_keyword, suggested_concept_id, frequency, examples, status)
```

> **Tránh concept "thùng rác"** quá chung như `EXPERIENCE_GOOD` — ai cũng muốn trải nghiệm tốt, nó không *phân biệt* được gì khi search. Concept phải mang tính lọc.

**Done khi:** ABSA trích đúng cặp khía cạnh–cảm xúc cho review tương phản; profile có score + evidence_count + smoothing; candidate queue + ngưỡng review hoạt động.

---

# SPRINT 3 — Knowledge Object Generation

> **Mục tiêu:** Đóng gói dữ liệu đã làm giàu thành knowledge object **chunk-aware** + định nghĩa **contract chunking/contextual** cho Khánh Duy. **Đây cũng là sprint chuyển sang real data (vd Agoda).**
> **Khung thời gian team:** trùng cuối **Sprint 2** (build trên mock) → **Sprint 3 (Tuần 5–6)** (real data + demo).

> **Ranh giới:** **Khánh Duy** code việc cắt chunk + embed. **Bạn** định nghĩa *cái gì* cần chunk, metadata nào kế thừa, câu ngữ cảnh dựng ra sao, và xuất `knowledge_objects.json`.

## Task 3.1 — Chunking Strategy · [BẠN tạo → Khánh Duy]

**Mục đích:** Mỗi loại tài liệu cắt theo cấu trúc tự nhiên — đây là **hợp đồng** với Khánh Duy.

```yaml
# config/chunking_strategy.yaml
strategies:
  review:        {mode: atomic}                 # 1 review = 1 chunk
  faq:           {mode: qa_pair}                # 1 chunk = 1 cặp hỏi-đáp (Agoda có 11 cặp)
  accommodation: {mode: semantic, by: section,  # tổng quan/phòng/tiện ích/vị trí
                  fallback: {size: 400, overlap: 60}}
  guide:         {mode: semantic, by: heading}
```

## Task 3.2 — Contextual Prefix · [BẠN tạo → Khánh Duy]

**Mục đích:** **Trước khi embed**, dán câu định vị chunk trong tài liệu cha (kỹ thuật *Contextual Retrieval* của Anthropic — giảm đáng kể truy xuất thất bại). **Tận dụng metadata đã có để dựng prefix rẻ** (template), chỉ dùng LLM cho chunk cần tóm tắt tinh tế.

```python
# src/build_objects.py
def cheap_context(obj, chunk):
    loc = obj["metadata"]["location"].get("area","")
    topic = {"amenity":"tiện ích","location":"vị trí","room":"phòng ốc","dining":"ẩm thực"}.get(chunk["covers_facet"],"")
    return f"Đoạn này thuộc mô tả {obj['title']} ({obj['type']} ở {loc}), nói về {topic}."

def build_embed_text(obj, chunk):
    return cheap_context(obj, chunk) + " " + chunk["text"]   # prefix + nội dung -> Khánh Duy embed
```

> Khánh Duy embed cái `embed_text` (đã có prefix), **không** phải `text` thô; và index `embed_text` cho cả **BM25** (contextual BM25) để hybrid của Anh Tài cũng hưởng lợi.

## Task 3.3 — Build knowledge_objects.json · [BẠN SỞ HỮU]

**Mục đích:** Tài liệu cuối. **Metadata sống sót nhờ ở 2 nơi:** `payload` (để **lọc**) + `embed_text` (để truy xuất **ngữ nghĩa**). Gắn kèm điểm profile để ranking dùng.

```json
{
  "id": "acc_vinpearl_nhatrang", "type": "resort", "title": "Vinpearl Resort Nha Trang",
  "source": "agoda", "content": "...",
  "metadata": {
    "object_type":"resort",
    "location":{"country":"VN","province":"khanh_hoa","area":"nha_trang"},
    "purpose":["family","romantic"], "amenity":["beachfront","private_pool","spa","kids_club"],
    "price_tier":"luxury", "star_rating":5
  },
  "tags": [
    {"concept":"AMEN_BEACHFRONT","confidence":0.98,"sources":["source_tag","rule"]},
    {"concept":"STYLE_QUIET","confidence":0.40,"sources":["review_profile"]}
  ],
  "chunks": [
    {
      "chunk_id":"acc_vinpearl_nhatrang#c2", "parent_id":"acc_vinpearl_nhatrang",
      "covers_facet":"amenity",
      "text":"Khu nghỉ có hồ bơi vô cực, spa và khu vui chơi trẻ em ...",
      "context_prefix":"Đoạn này thuộc mô tả Vinpearl Resort Nha Trang (resort 5 sao ở Nha Trang), nói về tiện ích.",
      "embed_text":"Đoạn này thuộc mô tả Vinpearl Resort Nha Trang (resort 5 sao ở Nha Trang), nói về tiện ích. Khu nghỉ có hồ bơi vô cực, spa và khu vui chơi trẻ em ...",
      "payload":{"object_type":"resort","area":"nha_trang","price_tier":"luxury",
                 "amenity":["beachfront","private_pool","spa","kids_club"],"purpose":["family","romantic"]}
    }
  ]
}
```

**Done khi:** đúng schema; mỗi chunk có `embed_text` (≠ `text`) + `payload` + `parent_id`; thống nhất schema với Khánh Duy.

## Task 3.4 — Hiểu output của bạn được dùng trong Search thế nào · [MODULE KHÁC: Anh Tài/Đạt — đọc để hiểu]

> Phần này **không phải bạn code**, nhưng phải hiểu để cấp đúng thứ.

```text
[Query NL] "resort yên tĩnh gần biển cho gia đình ở Nha Trang dưới 3tr"
   ↓ Query Understanding (DA09/Anh Tài)
   ↓ map sang concept (dùng synonym_dict của BẠN) + tách slot
{ location: nha_trang (FILTER), price ≤ 3tr (FILTER),
  concepts: [STYLE_QUIET, AMEN_BEACHFRONT, PURPOSE_FAMILY] (SCORE) }
   ↓ query expansion (rules của BẠN)
   ↓ Search (Đạt/Anh Tài) chạy SONG SONG:
        (1) FILTER payload theo facet  ── loại hẳn khách sạn ngoài Nha Trang / quá giá
        (2) HYBRID = BM25 + Vector trên CHUNK (đã contextual)  → RRF fusion
   ↓ Ranking (Anh Tài): Final = Semantic(khớp concept vs hotel PROFILE của BẠN)
                               + Popularity + Personalization + Business
   ↓ Context (top-K chunk + metadata + citation) → DA09
```

**Ba điều phải nhớ để cấp đúng:**
1. **Filter ≠ Score.** `location`/`budget` là **filter cứng** (payload) — khách sạn Đà Nẵng điểm cao vẫn bị *loại*, không phải xếp sau. Concept match là **điểm mềm**. → payload của bạn phải đủ trường để filter.
2. **Đây chỉ là nửa "structured".** Nửa kia là **hybrid vector+BM25 trên chunk** (của Khánh Duy + Anh Tài). Concept-matching đơn thuần thì giòn → chunk-aware + contextual của bạn (Task 3.1–3.3) là thứ nuôi nửa vector. Cả hai **fuse** bằng RRF.
3. **Score đến từ nhiều nguồn**, không chỉ review (xem Task 2.4b): tiện ích/sự thật từ structured; trải nghiệm từ review profile.

---

# SPRINT 4 — Evaluation & Feedback

> **Mục tiêu:** Đánh giá *chất lượng thật* lớp ngữ nghĩa + đóng vòng phản hồi. **Golden set do DA09 cấp; bạn + Kiên gán nhãn; Anh Tài/Kiên đo Recall/MRR/NDCG.** Bạn tập trung phần ngữ nghĩa.
> **Khung thời gian team:** trùng **Sprint 3 (Tuần 5–6)** — evaluation + demo.

## Task 4.1 — Ontology Coverage · [BẠN SỞ HỮU]
Đếm `% doc gắn được ≥ 1 concept`. **Done khi:** có con số + danh sách doc *không* gắn được (lỗ hổng vốn từ).

## Task 4.2 — Metadata Coverage · [BẠN SỞ HỮU]
Validate theo schema, đếm trường thiếu. **Done khi:** có con số + thống kê trường hay thiếu.

## Task 4.3 — Semantic Quality Review · [BẠN SỞ HỮU]
Tag **đúng/sai** (coverage cao ≠ đúng). Lấy mẫu từ **hàng đợi review** (conf thấp) + mẫu ngẫu nhiên conf cao; người chấm. Dùng `sources` (provenance) để biết tầng nào hay sai. **Done khi:** tỉ lệ chính xác ước lượng + lỗi phân theo tầng (source_tag/rule/embedding/llm).

## Task 4.4 — Đóng góp vào Retrieval Metrics · [BÀN GIAO → Anh Tài/Kiên]
Anh Tài đo Recall@10/MRR/NDCG (mục tiêu ≥ 0.8 / 0.7 / 0.75) so với BM25 baseline. **Vai trò bạn:** chạy **A/B lớp ngữ nghĩa** — bật/tắt synonym, expansion, contextual prefix, profile-boost — để xem lớp của bạn *cải thiện bao nhiêu*. **Done khi:** có bảng "chỉ số theo cấu hình lớp ngữ nghĩa" chứng minh đóng góp bằng số.

## Task 4.5 — Vòng phản hồi (ontology evolution) · [BẠN SỞ HỮU]

> **[BỔ SUNG]** Biến lớp ngữ nghĩa thành hệ thống sống — **nhưng có kiểm soát**.

```text
Nguồn tín hiệu: golden set + candidate queue + (sau này) log DA09
  - query 0 kết quả → thiếu synonym
  - keyword lặp nhiều chưa map được → candidate queue
  - expansion không cải thiện → bỏ
→ HUMAN duyệt candidate → sửa concepts.yaml → generate lại synonym/expansion
→ chạy golden set → tốt hơn MỚI merge (tăng version)
```

> **Tuyệt đối:** review/log **không** tự sửa ontology. Mọi thay đổi ontology qua human + golden set.

**Done khi:** có quy trình định kỳ rà candidate queue; `knowledge_report.md` tổng hợp coverage + quality + đóng góp metric.

---

# Phần cuối — Timeline, Deliverables, Quickstart, Checklist

## Ánh xạ 4 Sprint KE ↔ 3 Sprint team (2 tuần/sprint)

| Sprint team | Tuần | Việc KE của bạn | Mốc |
|---|---|---|---|
| **Team Sprint 1** | 1–2 | **KE Sprint 1** (Foundation): concepts, ontology, facets, normalize, synonym, expansion, **chốt metadata_schema** | Contract chốt cuối Tuần 1; làm trên **mock** |
| **Team Sprint 2** | 3–4 | **KE Sprint 2** (Enrichment): ontology_mapper, source-tag map, metadata_pipeline, ABSA + profile; **bắt đầu KE Sprint 3** (knowledge_objects trên mock) | Gán nhãn golden set (bạn+Kiên) cuối Tuần 1; walking skeleton chạy mock |
| **Team Sprint 3** | 5–6 | **KE Sprint 3 hoàn thiện** (real data vd Agoda + source-tag map) + **KE Sprint 4** (Evaluation, coverage, feedback) | Demo + đạt metric; báo cáo coverage |

## Deliverables (file của BẠN)

```text
config/  concepts.yaml · facets.yaml · ontology.yaml · synonym_dictionary.yaml
         query_expansion.yaml · metadata_schema.yaml(CONTRACT) · tagging_rules.yaml
         source_tag_map.yaml · chunking_strategy.yaml
src/     normalize.py · build_synonym_index.py · anchors.py · ontology_mapper.py
         absa.py · profile_builder.py · metadata_pipeline.py · build_objects.py · llm.py
output/  domain_analysis.md · knowledge_objects.json · hotel_semantic_profiles.json · knowledge_report.md
```

## Hai nguyên tắc xuyên suốt
1. **Mọi thay đổi đo được trên golden set** — không đo được thì không biết tốt hay tệ.
2. **Mọi output kèm `confidence` + `provenance`** — để module khác dùng thông minh và để bạn debug.

## Quickstart — tuần đầu (mock-first)

| Ngày | Việc | Ra cái gì |
|---|---|---|
| 1 | Đọc Phần 0 (đặc biệt 0.2 ranh giới, 0.5 ba thứ tách biệt) + dựng môi trường; sinh mock metadata từ schema | Repo chạy, mock data |
| 2 | Task 1.1 + 1.2: domain analysis + `concepts.yaml` (~30 concept, **trung tính**) | `domain_analysis.md`, `concepts.yaml` |
| 3 | Task 1.3 + 1.4: `normalize.py` + `facets.yaml` (có `da09_slot`) | nền tảng song ngữ + đa chiều |
| 4 | Task 1.6 + 1.7: sinh `synonym_dictionary` + `query_expansion`; chốt nháp `metadata_schema` | chuẩn bị contract |
| 5 | Chốt **3 contract** cùng team; thống nhất ai định nghĩa `metadata_schema` với DA09 | contract v1.0 |

## Checklist tổng

**Sprint 1 — Foundation**  _(trạng thái 2026-06-04 — chi tiết: `sprint1/SPRINT1_REPORT.md`)_
- [x] `concepts.yaml` ≥ 30 concept, **TRUNG TÍNH** — **73 concept**, tách 8 file `ontology/core/*.yaml`
- [x] `normalize.py` xử lý dấu + tách từ — `knowledge_engineering/common/normalize.py` (test 15/15)
- [x] `facets.yaml` đủ facet + `cardinality` + `da09_slot` (+ `metadata_field`)
- [x] `ontology.yaml` có quan hệ `near`/`located_in` — 22 quan hệ `near` (tự sinh)
- [x] `synonym_dictionary.yaml` ≥ 100 form (kể cả bỏ dấu) → Anh Tài — **543 form**
- [~] `query_expansion.yaml` ≥ 20 rule → Anh Tài — **21 rule ĐỦ số nhưng `unverified`**; phần "đã kiểm golden set" CHỜ golden set DA09
- [x] `metadata_schema.yaml` chốt CONTRACT v1.0, đồng bộ DA09 — + pydantic validate; metadata.md đồng bộ concept_id

**Sprint 2 — Enrichment**
- [ ] `ontology_mapper.py` 3 tầng + fuse, tag có confidence + sources, xử lý phủ định
- [ ] `source_tag_map.yaml` map vocabulary nguồn (Agoda...) → concept
- [ ] `metadata_pipeline.py` map/validate/đối chiếu (xử lý mâu thuẫn kiểu `is_luxury`)
- [ ] ABSA trích đúng cặp khía cạnh–cảm xúc; concept TRUNG TÍNH + sentiment riêng
- [ ] `hotel_semantic_profiles.json` có score + smoothing (Wilson) + evidence_count; phân biệt presence vs sentiment; seed từ crawl aggregates
- [ ] Lớp dữ liệu tách (evidence / profile / candidate_queue); ngưỡng review

**Sprint 3 — Knowledge Object**
- [ ] `chunking_strategy.yaml` theo loại → bàn giao Khánh Duy
- [ ] Logic `context_prefix` rẻ từ metadata → bàn giao Khánh Duy
- [ ] `knowledge_objects.json` đúng schema: `embed_text` (≠ `text`) + `payload` + `parent_id` + tag/profile
- [ ] Hiểu luồng search (filter≠score, hybrid, multi-source) để cấp đúng payload/vocabulary
- [ ] Chạy thử end-to-end 1 object với Khánh Duy + Anh Tài

**Sprint 4 — Evaluation**
- [ ] Ontology coverage + Metadata coverage (con số + lỗ hổng)
- [ ] Semantic quality review (tỉ lệ đúng + lỗi theo tầng)
- [ ] A/B đóng góp lớp ngữ nghĩa vào Recall/MRR/NDCG (cùng Anh Tài/Kiên)
- [ ] Quy trình rà candidate queue; ontology chỉ đổi qua human + golden set
- [ ] `knowledge_report.md` tổng hợp

---

*Hết. Bản này tích hợp: ba-thứ-tách-biệt (ontology/profile/evidence), luồng review production + ABSA concept-trung-tính + score có smoothing, source-tag mapping cho data crawl, luồng search (filter vs score + hybrid + multi-source), và ranh giới module theo kế hoạch team (mock-first, 3 contract, 4 KE sprint ↔ 3 team sprint).*

```