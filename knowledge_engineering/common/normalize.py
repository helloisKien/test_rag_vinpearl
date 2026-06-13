"""Chuẩn hóa tiếng Việt — Task 1.3 (Sprint 1), DA10 Knowledge Engineering.

Owner: Trương Anh Long. DÙNG CHUNG: áp cho CẢ query (lúc search) lẫn nhãn/surface_form
(lúc build synonym) theo CÙNG một quy trình, để chúng khớp được vào nhau.
(Thống nhất một bản với Anh Tài / Data Quality.)

Ba việc theo đúng thiết kế DA10:
    1. NFC      — gộp dấu tổ hợp về dạng dựng sẵn (chữ "ề" tổ hợp vs dựng sẵn phải bằng nhau).
    2. segment  — tách từ ghép tiếng Việt ("hồ bơi" -> "hồ_bơi") bằng underthesea.
    3. fold     — biến thể bỏ dấu ("gần biển" -> "gan bien", "đ" -> "d") để match query gõ không dấu.

normalize(t)              -> dạng có dấu, đã tách từ, lowercase.
normalize(t, fold=True)   -> thêm bước bỏ dấu.

Lý do tách fold thành tham số: synonym_dictionary (Task 1.6) index CẢ hai dạng cho mỗi
surface form, nên query "resort gan bien" (không dấu) lẫn "resort gần biển" (có dấu) đều trỏ
về cùng concept.
"""

import unicodedata

from underthesea import word_tokenize


def to_nfc(t: str) -> str:
    """Chuẩn hóa Unicode về NFC (dấu dựng sẵn). Tránh 'ề' tổ hợp != 'ề' dựng sẵn."""
    return unicodedata.normalize("NFC", t)


def strip_diacritics(t: str) -> str:
    """Bỏ dấu tiếng Việt: 'gần biển' -> 'gan bien'. Xử lý riêng đ/Đ (không phải dấu tổ hợp)."""
    nfd = unicodedata.normalize("NFD", t)
    out = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return out.replace("đ", "d").replace("Đ", "D")


def segment(t: str) -> str:
    """Tách từ tiếng Việt, nối từ ghép bằng '_': 'hồ bơi' -> 'hồ_bơi'."""
    return word_tokenize(t, format="text")


def normalize(t: str, fold: bool = False) -> str:
    """Chuẩn hóa một chuỗi (query hoặc nhãn) theo quy trình DA10.

    Thứ tự: NFC -> lowercase -> strip -> segment (tách từ). Nếu fold=True thì bỏ dấu sau cùng.

    Lưu ý thứ tự: bỏ dấu SAU khi tách từ, vì underthesea cần dấu để tách đúng;
    bỏ dấu trước sẽ làm tách từ kém chính xác.

    QUAN TRỌNG (separator nhất quán ở dạng fold): underthesea tách từ ghép DỰA VÀO DẤU,
    nên "yên tĩnh" -> "yên_tĩnh" (nối _) còn query gõ không dấu "yen tinh" -> "yen tinh"
    (không nối). Nếu giữ nguyên thì "yen_tinh" != "yen tinh" và query không khớp synonym.
    Vì vậy ở dạng fold ta GỘP separator về khoảng trắng (đưa "_" về " "), để nhãn-fold và
    query-fold luôn dùng cùng quy ước. Dạng có dấu (fold=False) giữ "_" để bảo toàn ranh giới
    từ ghép cho các bước cần (vd contextual/BM25).
    """
    t = segment(to_nfc(t).lower().strip())
    if fold:
        t = strip_diacritics(t).replace("_", " ")
    return t
