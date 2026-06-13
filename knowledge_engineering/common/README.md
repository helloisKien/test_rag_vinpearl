# common — Tiện ích dùng chung (DA10 Knowledge Engineering)

Các hàm dùng chung cho nhiều module KE (enrichment, entity_extraction, metadata_extraction...).

## `normalize.py` — Chuẩn hóa tiếng Việt (Task 1.3, Sprint 1)

Áp **cùng một quy trình** cho cả query (lúc search) lẫn nhãn/surface_form (lúc build synonym),
để hai bên khớp được vào nhau.

```python
from knowledge_engineering.common import normalize

normalize("Resort Gần Biển")             # -> 'resort gần biển'  (NFC + lowercase + tách từ)
normalize("Resort Gần Biển", fold=True)  # -> 'resort gan bien'  (thêm bỏ dấu, separator về space)
```

Ba bước: **NFC** (gộp dấu tổ hợp) → **segment** (tách từ ghép bằng underthesea, "hồ bơi" → "hồ_bơi")
→ **fold** (tùy chọn: bỏ dấu, đ→d, và gộp "_" về " ").

**Vì sao fold gộp `_` về khoảng trắng:** underthesea tách từ ghép dựa vào dấu, nên nhãn có dấu
("yên tĩnh" → "yên_tĩnh") và query gõ không dấu ("yen tinh" → "yen tinh") ra separator khác nhau.
Gộp về space ở dạng fold để query không dấu vẫn khớp synonym. Dạng có dấu giữ "_" để bảo toàn
ranh giới từ ghép cho BM25/contextual.

Phụ thuộc: `underthesea` (đã cài trong `.venv`). Chạy bằng `.venv/Scripts/python.exe`.

Đã test: done-criteria DA10 + 15 surface form thật từ `ontology/core/*.yaml` (15/15 pass).
