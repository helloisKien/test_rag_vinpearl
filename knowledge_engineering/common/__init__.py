"""Tiện ích dùng chung cho Knowledge Engineering (DA10).

Hiện có:
- normalize: chuẩn hóa tiếng Việt (NFC + tách từ + biến thể bỏ dấu).
"""

from .normalize import normalize, to_nfc, strip_diacritics, segment

__all__ = ["normalize", "to_nfc", "strip_diacritics", "segment"]
