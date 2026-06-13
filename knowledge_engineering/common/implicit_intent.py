"""implicit_intent.py — suy concept từ MÔ TẢ HOÀN CẢNH (intent ngầm) — Sprint 2.

VẤN ĐỀ: synonym_dictionary chỉ khớp surface form CỐ ĐỊNH ("gia đình", "cặp đôi"...).
Người dùng thật hay MÔ TẢ hoàn cảnh thay vì gọi tên concept:
    "nhà tôi có 2 con"            -> PURPOSE_FAMILY   (không có form nào khớp "2 con")
    "đi với vợ con"               -> PURPOSE_FAMILY
    "hai vợ chồng đi nghỉ"        -> PURPOSE_ROMANTIC
    "nhóm 6 đứa bạn"              -> PURPOSE_GROUP
Những cách nói này CHỨA BIẾN SỐ ("2 con", "6 đứa") nên KHÔNG liệt kê hết được vào
surface_forms — phải bắt bằng PATTERN.

THIẾT KẾ: một BẢNG LUẬT khai báo (RULES). Mỗi luật = (regex, [concept_id...]). Match trên
câu đã normalize ở CẢ hai dạng (có dấu + bỏ dấu), giống parse_concepts, để query gõ kiểu nào
cũng bắt được. Module DÙNG CHUNG: query_demo (test tay) và tầng search production (Anh Tài/Đạt)
gọi cùng một hàm -> không lặp logic 2 nơi.

NGUYÊN TẮC: chỉ suy ra concept SOFT (purpose/style) — dùng để ƯU TIÊN ranking + expand, KHÔNG
lọc cứng. Concept HARD (amenity/setting) vẫn lấy từ surface form (rõ ràng có/không), không đoán.

Mở rộng: thêm dòng vào RULES. Mỗi dòng nên kèm ví dụ câu trong comment để người sau hiểu.

Dùng:
    from knowledge_engineering.common.implicit_intent import parse_implicit_intent
    parse_implicit_intent("nhà tôi có 2 con")  -> {"PURPOSE_FAMILY": "có 2 con"}
"""

from __future__ import annotations

import re

from knowledge_engineering.common.normalize import normalize

# Định lượng đứng trước danh từ đếm người: số (1-2 chữ số) hoặc chữ "một/hai/.../vài/mấy".
# Viết sẵn 2 biến thể CÓ DẤU và BỎ DẤU vì ta match trên cả hai dạng normalize.
_QTY = r"(?:\d{1,2}|một|hai|ba|bốn|năm|sáu|bảy|vài|mấy|đứa|những)"
_QTY_F = r"(?:\d{1,2}|mot|hai|ba|bon|nam|sau|bay|vai|may|dua|nhung)"

# Mỗi luật: (mô tả, regex_có_dấu, regex_bỏ_dấu, [concept_id...]).
# regex áp lên chuỗi đã normalize (đã tách từ -> token cách nhau bởi space; KHÔNG có "_" ở
# dạng fold). Dùng \b lỏng bằng cách bao space/biên; ưu tiên cụm rõ nghĩa để tránh false match.
RULES: list[tuple[str, str, str, list[str]]] = [
    # ── PURPOSE_FAMILY: đi cùng con/cháu/em bé (có định lượng hoặc "có ...") ──────
    # "nhà tôi có 2 con", "đi với 1 bé", "mang theo 2 đứa nhỏ", "có em bé", "vợ con"
    (
        "đi cùng con/cháu/bé (kèm số lượng)",
        rf"{_QTY}\s*(?:con|bé|cháu|nhóc|em bé|trẻ|nhỏ)\b",
        rf"{_QTY_F}\s*(?:con|be|chau|nhoc|em be|tre|nho)\b",
        ["PURPOSE_FAMILY"],
    ),
    (
        "có con / vợ con / con nhỏ (không cần số)",
        r"\b(?:có con|vợ con|chồng con|con nhỏ|con cái|em bé|trẻ nhỏ|tụi nhỏ|bọn trẻ|các bé|mấy đứa nhỏ)\b",
        r"\b(?:co con|vo con|chong con|con nho|con cai|em be|tre nho|tui nho|bon tre|cac be|may dua nho)\b",
        ["PURPOSE_FAMILY"],
    ),
    # ── PURPOSE_ROMANTIC: cặp đôi / vợ chồng / người yêu ────────────────────────
    # "hai vợ chồng", "đi với người yêu", "vợ chồng son", "kỷ niệm ngày cưới"
    (
        "vợ chồng / người yêu / hẹn hò",
        r"\b(?:hai vợ chồng|vợ chồng son|vợ chồng trẻ|với người yêu|với bạn gái|với bạn trai|"
        r"kỷ niệm ngày cưới|kỷ niệm cưới|đi hẹn hò|hai đứa)\b",
        r"\b(?:hai vo chong|vo chong son|vo chong tre|voi nguoi yeu|voi ban gai|voi ban trai|"
        r"ky niem ngay cuoi|ky niem cuoi|di hen ho|hai dua)\b",
        ["PURPOSE_ROMANTIC"],
    ),
    # ── PURPOSE_GROUP: nhóm bạn / đoàn (có định lượng người) ────────────────────
    # "nhóm 6 đứa bạn", "đi với đám bạn", "hội bạn 10 người", "team building công ty"
    (
        "nhóm / đám / hội bạn",
        r"\b(?:nhóm bạn|đám bạn|hội bạn|cả nhóm|cả hội|đi với bạn bè|nhóm \d+ người|"
        r"\d+ đứa bạn|đoàn \d+ người|team building)\b",
        r"\b(?:nhom ban|dam ban|hoi ban|ca nhom|ca hoi|di voi ban be|nhom \d+ nguoi|"
        r"\d+ dua ban|doan \d+ nguoi|team building)\b",
        ["PURPOSE_GROUP"],
    ),
    # ── PURPOSE_BUSINESS: công tác / hội nghị ───────────────────────────────────
    # "đi công tác", "dự hội nghị", "đi họp ở", "chuyến công tác"
    (
        "công tác / hội nghị / đi họp",
        r"\b(?:đi công tác|chuyến công tác|dự hội nghị|dự hội thảo|đi hội thảo|đi họp|đi công chuyện)\b",
        r"\b(?:di cong tac|chuyen cong tac|du hoi nghi|du hoi thao|di hoi thao|di hop|di cong chuyen)\b",
        ["PURPOSE_BUSINESS"],
    ),
    # ── PURPOSE_WELLNESS: nghỉ ngơi / xả stress ─────────────────────────────────
    # "cần nghỉ ngơi", "muốn xả stress", "đi dưỡng sức"
    (
        "nghỉ ngơi / xả stress / dưỡng sức",
        r"\b(?:cần nghỉ ngơi|muốn nghỉ ngơi|xả stress|xả hơi|dưỡng sức|an dưỡng|tĩnh dưỡng)\b",
        r"\b(?:can nghi ngoi|muon nghi ngoi|xa stress|xa hoi|duong suc|an duong|tinh duong)\b",
        ["PURPOSE_WELLNESS"],
    ),
]


def parse_implicit_intent(q: str) -> dict[str, str]:
    """Suy concept_id từ mô tả hoàn cảnh trong câu.

    Trả dict {concept_id: bằng-chứng-khớp} — bằng chứng là cụm text đã match (để giải thích
    được "vì sao gán nhãn này"). Match trên câu normalize CÓ DẤU và BỎ DẤU. Nếu một concept
    khớp nhiều luật, giữ bằng chứng đầu tiên.
    """
    norm = normalize(q)
    normf = normalize(q, fold=True)
    out: dict[str, str] = {}
    for _desc, rx, rxf, cids in RULES:
        m = re.search(rx, norm) or re.search(rxf, normf)
        if not m:
            continue
        for cid in cids:
            out.setdefault(cid, m.group(0).strip())
    return out


if __name__ == "__main__":
    for q in [
        "tìm khách sạn ở phú quốc, nhà tôi có 2 con",
        "hai vợ chồng đi nghỉ cuối tuần",
        "nhóm 6 đứa bạn đi phú quốc",
        "đi công tác hà nội cần phòng yên tĩnh",
        "cần nghỉ ngơi xả stress",
        "khách sạn có hồ bơi ở đà nẵng",  # không có intent ngầm -> {}
    ]:
        print(f"{q!r:55s} -> {parse_implicit_intent(q)}")
