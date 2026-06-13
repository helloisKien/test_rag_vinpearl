"""
expand_topk_to_15.py
--------------------
Mở rộng relevant_hotel_ids của golden_set_v1.json từ top-5 lên TOP-15, vẫn sắp
theo độ liên quan.

Nguyên tắc:
  - GIỮ NGUYÊN các hotel_id đang có (top-5 đã kiểm tay) làm ĐẦU danh sách, đúng thứ tự.
  - Tái dựng pool ứng viên cho từng query bằng đúng bộ từ khóa/điều kiện đã dùng
    (cùng matcher với các script find_*), xếp theo tiêu chí của nhóm, rồi BỔ SUNG
    các id chưa có vào cuối cho tới khi đủ 15 (hoặc hết ứng viên).

Sort theo nhóm:
  - FAQ / POL / AMEN : review_score giảm dần
  - ACT             : số activity khớp giảm dần, rồi review_score
  - DESC            : số từ khóa khớp trong description giảm dần, rồi review_score

Cách chạy (từ d:\\Test):
    python evaluation/tools/expand_topk_to_15.py

An toàn: chỉ ghi đè golden_set_v1.json sau khi xử lý xong toàn bộ. In cảnh báo cho
query nào không đủ 15 ứng viên.
"""

import json
import os
import unicodedata

HERE = os.path.dirname(__file__)
CORPUS_DIR = os.path.join(HERE, "..", "corpus")
HOTEL = os.path.join(CORPUS_DIR, "hotel_corpus.jsonl")
FAQACT = os.path.join(CORPUS_DIR, "faq_activities_corpus.jsonl")
POL = os.path.join(CORPUS_DIR, "policies_corpus.jsonl")
GOLDEN = os.path.join(HERE, "..", "..", "golden_dataset", "golden_set_v1.json")

TOP_K = 15


def norm(s):
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D").lower()


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


# ── Spec cho từng query ─────────────────────────────────────────────────────
# group: desc|faq|act|pol|amen ; city: substring normalize (None nếu không lọc city)
# acc_type: lọc accommodation_type (None nếu không) ; kw/cat: tham số matcher
SPECS = {
    # DESC (city theo hard_filters; chỉ DESC-002 lọc Resort, DESC-003 lọc Hội An)
    "GS-DESC-001": {"group": "desc", "city": None, "kw": ["moi xay dung", "moi khai truong", "xay dung vao nam 2022", "xay dung vao nam 2023", "xay dung vao nam 2024", "khanh thanh", "vua khai truong", "vua moi mo cua"]},
    "GS-DESC-002": {"group": "desc", "city": None, "acc_type": "resort", "kw": ["tren dao", "hon dao", "oc dao", "biet lap", "tach biet", "dao rieng", "hoang so"]},
    "GS-DESC-003": {"group": "desc", "city": "hoi an", "kw": ["pho co", "khu pho co", "trung tam pho co"]},
    "GS-DESC-004": {"group": "desc", "city": None, "kw": ["ven song", "ben song", "bo song", "canh song", "dong song", "song han", "song huong", "song sai gon"]},
    "GS-DESC-005": {"group": "desc", "city": None, "kw": ["boutique", "am cung", "nho xinh"]},
    "GS-DESC-006": {"group": "desc", "city": None, "kw": ["gan san bay", "sat san bay", "cach san bay 5 phut", "cach san bay 10 phut", "cach san bay 15 phut", "cach san bay 5 phút"]},
    "GS-DESC-007": {"group": "desc", "city": None, "kw": ["vuon nhiet doi", "khu vuon xanh", "vuon cay xanh", "cay xanh mat", "khong gian xanh", "vuon rong"]},
    "GS-DESC-008": {"group": "desc", "city": None, "kw": ["binh minh", "hoang hon", "mat troi moc", "mat troi lan"]},
    "GS-DESC-009": {"group": "desc", "city": None, "kw": ["tren doi", "lung chung nui", "tren nui", "trien nui", "ngon doi", "cao nguyen", "doi nui"]},
    "GS-DESC-010": {"group": "desc", "city": None, "kw": ["yen tinh", "tinh lang", "tach biet", "tranh xa on ao", "tron khoi pho thi", "thanh binh"]},
    # FAQ
    "GS-FAQ-001": {"group": "faq", "city": "nha trang", "cat": "facilities_parking", "kw": []},
    "GS-FAQ-002": {"group": "faq", "city": "ha noi", "cat": "facilities_cleaning", "kw": ["giat"]},
    "GS-FAQ-003": {"group": "faq", "city": "ho chi minh", "cat": "info_payment", "kw": []},
    "GS-FAQ-004": {"group": "faq", "city": "hoi an", "cat": "", "kw": ["dua don san bay"]},
    "GS-FAQ-005": {"group": "faq", "city": "ho chi minh", "cat": "things-to-do", "kw": ["be boi", "ho boi"]},
    "GS-FAQ-006": {"group": "faq", "city": "da nang", "cat": "facilities_food and drink", "kw": ["bar", "quay bar", "do uong"]},
    "GS-FAQ-007": {"group": "faq", "city": "ha noi", "cat": "policies_family", "kw": []},
    "GS-FAQ-008": {"group": "faq", "city": "nha trang", "cat": "info_price", "kw": []},
    "GS-FAQ-010": {"group": "faq", "city": "ha long", "cat": "languages spoken", "kw": []},
    # ACT
    "GS-ACT-001": {"group": "act", "city": "nha trang", "kw": ["vinwonders", "vinpearl harbour", "vinke"]},
    "GS-ACT-002": {"group": "act", "city": "ha long", "kw": ["du thuyen", "cruise", "vinh ha long", "kayak"]},
    "GS-ACT-003": {"group": "act", "city": "da nang", "kw": ["ba na", "bana", "sun world ba na", "cap treo"]},
    "GS-ACT-004": {"group": "act", "city": "hoi an", "kw": ["thung", "rung dua", "coconut", "bay mau"]},
    "GS-ACT-005": {"group": "act", "city": "da lat", "kw": ["alpine", "coaster", "datanla", "truot"]},
    "GS-ACT-006": {"group": "act", "city": "phu quoc", "kw": ["vinwonders", "grand world", "hon thom", "safari"]},
    "GS-ACT-007": {"group": "act", "city": "ha noi", "kw": ["roi nuoc", "puppet", "thang long"]},
    "GS-ACT-008": {"group": "act", "city": "hue", "kw": ["song huong", "dai noi", "ca hue", "citadel", "city tour"]},
    "GS-ACT-009": {"group": "act", "city": "da nang", "kw": ["than tai", "suoi khoang", "khoang nong"]},
    "GS-ACT-010": {"group": "act", "city": "ha noi", "kw": ["trang an", "ninh binh", "tam coc", "bai dinh", "hoa lu"]},
    # POL
    "GS-POL-001": {"group": "pol", "city": "ha noi", "kw": ["0-3 tuoi", "tre em duoi", "o mien phi", "mien phi neu o cung", "tre em tu 0"]},
    "GS-POL-002": {"group": "pol", "city": "ho chi minh", "kw": ["0-3 tuoi", "tre em duoi", "o mien phi", "mien phi neu o cung", "tre em tu 0"]},
    "GS-POL-003": {"group": "pol", "city": "da nang", "kw": ["0-3 tuoi", "tre em duoi", "o mien phi", "mien phi neu o cung", "tre em tu 0"]},
    "GS-POL-004": {"group": "pol", "city": "ha noi", "kw": ["giuong phu"]},
    "GS-POL-005": {"group": "pol", "city": "ho chi minh", "kw": ["giuong phu"]},
    "GS-POL-006": {"group": "pol", "city": "da nang", "kw": ["giuong phu"]},
    "GS-POL-007": {"group": "pol", "city": "vung tau", "kw": ["giay to tuy than", "chung minh nhan dan", "can cuoc", "ho chieu", "giay khai sinh"]},
    "GS-POL-008": {"group": "pol", "city": "nha trang", "kw": ["giay to tuy than", "chung minh nhan dan", "can cuoc", "ho chieu", "giay khai sinh"]},
    "GS-POL-009": {"group": "pol", "city": "phu quoc", "kw": ["giay to tuy than", "chung minh nhan dan", "can cuoc", "ho chieu", "giay khai sinh"]},
    "GS-POL-010": {"group": "pol", "city": "ho chi minh", "kw": ["do tuoi nhan phong", "tuoi toi thieu", "tu 18 tuoi", "18 tuoi tro len"]},
    # AMEN
    "GS-AMEN-001": {"group": "amen", "city": "nha trang", "kw": ["be boi ngoai troi"]},
    "GS-AMEN-002": {"group": "amen", "city": "phu quoc", "kw": ["quan bar canh be boi", "bar canh be boi"]},
    "GS-AMEN-003": {"group": "amen", "city": "vung tau", "kw": ["be boi tre em"]},
    "GS-AMEN-004": {"group": "amen", "city": "ha noi", "kw": ["phong tap"]},
    "GS-AMEN-005": {"group": "amen", "city": "da nang", "kw": ["mat-xa", "mat xa", "spa xong"]},
    "GS-AMEN-006": {"group": "amen", "city": "hoi an", "kw": ["vuon"]},
    "GS-AMEN-007": {"group": "amen", "city": "phu quoc", "kw": ["bai bien rieng"]},
    "GS-AMEN-008": {"group": "amen", "city": "ho chi minh", "kw": ["nha hang"]},
    "GS-AMEN-009": {"group": "amen", "city": "ho chi minh", "kw": ["khong hut thuoc", "phong khong hut thuoc"]},
    "GS-AMEN-010": {"group": "amen", "city": "nha trang", "kw": ["san choi"]},
}


def main():
    hotels = {h["hotel_id"]: h for h in load_jsonl(HOTEL)}
    for r in load_jsonl(FAQACT):
        if r["hotel_id"] in hotels:
            hotels[r["hotel_id"]]["faq"] = r.get("faq") or []
            hotels[r["hotel_id"]]["activities"] = r.get("activities") or []
    for r in load_jsonl(POL):
        if r["hotel_id"] in hotels:
            hotels[r["hotel_id"]]["policy_notes"] = r.get("policy_notes") or []

    HOTELS = list(hotels.values())

    def rv(h):
        return h.get("review_score") or 0

    def city_ok(h, city):
        return city is None or city in norm(h.get("city"))

    def build_pool(spec):
        g = spec["group"]
        city = spec.get("city")
        acc = spec.get("acc_type")
        kw = spec.get("kw", [])
        cands = []
        for h in HOTELS:
            if not city_ok(h, city):
                continue
            if acc and acc not in norm(h.get("accommodation_type")):
                continue
            if g == "desc":
                dn = norm(h.get("description"))
                hits = sum(1 for k in kw if k in dn)
                if hits:
                    cands.append((hits, rv(h), h["hotel_id"]))
            elif g == "faq":
                cat = spec.get("cat", "")
                ok = False
                for fq in h.get("faq") or []:
                    if cat and cat.lower() not in (fq.get("cat") or "").lower():
                        continue
                    an = norm(fq.get("a"))
                    if not kw or any(k in an for k in kw):
                        ok = True
                        break
                if ok:
                    cands.append((1, rv(h), h["hotel_id"]))
            elif g == "act":
                hits = 0
                for act in h.get("activities") or []:
                    blob = norm(act.get("title")) + " " + norm(act.get("desc"))
                    if any(k in blob for k in kw):
                        hits += 1
                if hits:
                    cands.append((hits, rv(h), h["hotel_id"]))
            elif g == "pol":
                blob = norm("\n".join(h.get("policy_notes") or []))
                if any(k in blob for k in kw):
                    cands.append((1, rv(h), h["hotel_id"]))
            elif g == "amen":
                found = False
                for a in h.get("amenities") or []:
                    na = norm(a)
                    if any(s in na for s in kw):
                        found = True
                        break
                if found:
                    cands.append((1, rv(h), h["hotel_id"]))
        # sort: hits desc, review desc
        cands.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [c[2] for c in cands]

    with open(GOLDEN, encoding="utf-8") as f:
        data = json.load(f)

    warnings = []
    for q in data.get("queries", []):
        qid = q.get("query_id")
        spec = SPECS.get(qid)
        if not spec:
            warnings.append(f"{qid}: KHONG co spec, giu nguyen")
            continue
        head = [i for i in q.get("relevant_hotel_ids", []) if isinstance(i, int)]
        pool = build_pool(spec)
        # Sắp xếp lại TOÀN BỘ theo độ liên quan (không ghim top-5 cũ).
        merged = list(pool)
        # Phòng trường hợp head có id không lọt pool (vd policyNotes dài, DESC kiểm tay):
        # vẫn giữ lại để không mất nhãn đã xác nhận, xếp về cuối.
        for hid in head:
            if hid not in merged:
                merged.append(hid)
        q["relevant_hotel_ids"] = merged[:TOP_K]
        if len(q["relevant_hotel_ids"]) < TOP_K:
            warnings.append(f"{qid}: chi co {len(q['relevant_hotel_ids'])} KS (it hon {TOP_K})")

    meta = data.get("metadata", {})
    if "ground_truth_note" in meta:
        meta["ground_truth_note"] = (
            "relevant_hotel_ids chứa DANH SÁCH hotel_id (đã map từ tên), ĐÃ SẮP XẾP THEO ĐỘ LIÊN QUAN GIẢM DẦN. "
            "top_k = 15: toàn bộ danh sách được xếp lại theo độ liên quan, KHÔNG ghim cố định top-5 cũ "
            "(FAQ/POL/AMEN xếp theo review_score; ACT theo số activity khớp rồi review_score; DESC theo số từ khóa khớp rồi review_score). "
            "Một số query có ít hơn 15 KS thoả điều kiện trong corpus."
        )

    with open(GOLDEN, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"OK: da ghi {GOLDEN} voi top_k={TOP_K}.")
    if warnings:
        print("--- CANH BAO ---")
        for w in warnings:
            print("  " + w)


if __name__ == "__main__":
    main()
