# enrichment

Phân loại theo taxonomy và làm giàu thuộc tính (Layer 3) — Sprint 2.

Sinh `knowledge_object` (HARD + SOFT) cho 520 hotel từ `data/cleaned/` + `ontology/`.

## Dựng lại từ đầu sau khi pull

Các file `*.json` trong thư mục này là **artifact, KHÔNG commit vào git** (xem `.gitignore`).
Sau khi pull, đồng đội phải **tự sinh lại** — mọi input đã có sẵn trong git
(`data/cleaned/` 520 hotel, `ontology/`, `synonym_dictionary.yaml`) và **không bước nào tốn
tiền** (đều là rule thuần, không gọi LLM).

Chạy bằng venv python, **đúng thứ tự** (Windows PowerShell):

```powershell
# 0. (chỉ lần đầu) cài dependencies — cần underthesea, pyyaml...
.venv\Scripts\pip install -r requirements.txt

# 1. synonym dictionary — ontology/synonym_dictionary.yaml ĐÃ tracked; chỉ build lại
#    khi bạn SỬA ontology/core/*.yaml (sửa surface_forms phải build lại — bẫy fold đồng âm)
.venv\Scripts\python.exe -X utf8 -m knowledge_engineering.common.build_synonym_index

# 2. Sinh 3 input trung gian (đều đọc data/cleaned/*.json, KHÔNG tốn tiền):
.venv\Scripts\python.exe -X utf8 -m knowledge_engineering.enrichment.ontology_mapper      # -> hotel_tags.json
.venv\Scripts\python.exe -X utf8 -m knowledge_engineering.enrichment.metadata_pipeline    # -> hotel_metadata.json
.venv\Scripts\python.exe -X utf8 -m knowledge_engineering.enrichment.profile_builder      # -> hotel_profiles.json

# 3. Gộp tag + metadata + profile -> knowledge_objects.json (cái query_demo đọc):
.venv\Scripts\python.exe -X utf8 -m knowledge_engineering.enrichment.build_objects

# 4. Thử công cụ test tay:
.venv\Scripts\python.exe -X utf8 -m knowledge_engineering.enrichment.query_demo "nhà tôi có 2 con đi phú quốc"
```

**Thứ tự bắt buộc:** synonym → (mapper + metadata + profile) → build_objects → query_demo.
Bước 3 cần CẢ BA file của bước 2.

## Pipeline

```
ontology/core/*.yaml ──build_synonym_index──► synonym_dictionary.yaml (tracked)
                                                       │
data/cleaned/hotel_*.json ──ontology_mapper────► hotel_tags.json      │
                          ──metadata_pipeline──► hotel_metadata.json   │
                          ──profile_builder────► hotel_profiles.json   │
                                                       └──build_objects─┴─► knowledge_objects.json
                                                                                      │
                                                                          query_demo ◄┘ (test tay)
```

## File trong thư mục

| File | Vai trò | LLM? |
|---|---|---|
| `ontology_mapper.py` | Tầng 0/1: structured field + quét text qua synonym → tag concept | không |
| `metadata_pipeline.py` | Map/reconcile metadata (giá, sao, location, nearby) | không |
| `profile_builder.py` | SOFT profile (style/aspect score) từ `reviews_detail.tags` | không |
| `build_objects.py` | Gộp tag + metadata + profile → `knowledge_objects.json` | không |
| `query_demo.py` | Công cụ test tay chất lượng nhãn (mô phỏng filter tầng search) | không |
| `absa.py` | **TÙY CHỌN** — ABSA per-review, *thêm* evidence vào profile | **CÓ (tốn tiền)** |
| `llm.py` | Client đa-provider cho `absa.py` | — |

**`absa.py` KHÔNG bắt buộc** để dựng lại: `query_demo` chạy đủ tốt với profile cơ bản (sinh
miễn phí từ `reviews_detail.tags` ở bước `profile_builder`). Chỉ chạy ABSA khi cần evidence
chi tiết per-review — và chạy theo bản AN TOÀN chống tốn tiền (xem `absa.py`).

## Hiểu query "mô tả hoàn cảnh"

`query_demo` + `knowledge_engineering/common/implicit_intent.py` xử lý câu mô tả gián tiếp
("nhà tôi có 2 con" → PURPOSE_FAMILY) qua 2 cơ chế: surface_forms tĩnh + pattern regex.
Chi tiết: `docs2/reports/ontology/sprint2/step1b_surface_form_audit.md` (Đợt 2).
