"""build_locations.py — TỰ SINH location ontology (Việt Nam) từ data. Lớp A (Task 1.5 mở rộng).

Owner: Trương Anh Long (Knowledge Engineering, DA10).

PHẠM VI: CHỈ VIỆT NAM (chốt cuối: VOTA target VN; data đã lọc bỏ hotel nước ngoài, còn 520 hotel
VN). Script quét field địa lý THẬT trong data/cleaned rồi sinh concept LOC_* phân cấp
country > province > city > area. Cây country vẫn giữ (chỉ LOC_VIETNAM) để sau này muốn thêm
nước thì không phải đập cấu trúc; cơ chế auto-slug country lạ (Mức 3) cũng giữ để an toàn.

CÂY (độ phân giải theo data Agoda):
    country  (kind: country)  <- field `country`        (luôn = LOC_VIETNAM)
      province (kind: place)  <- TÁCH từ "City (Tỉnh)"  (vd "Quy Nhơn (Bình Định)" -> Bình Định)
        city   (kind: place)  <- field `city`           (gộp `province` field vì Agoda lẫn lộn)
          area (kind: area)   <- field `area`           (gộp `district`, vì area==district)
Tầng tỉnh CHỈ sinh khi tên city có tỉnh trong ngoặc (hoặc trước dấu '/') — tách tự động, không
đoán. City không có tỉnh -> parent thẳng LOC_VIETNAM. Lý do gộp province-field/district: Agoda
crawl province==city và district==area gần 100% -> sinh đủ sẽ trùng; giữ đúng độ phân giải thật.

LANDMARK (LMK_*): cũng TỰ SINH từ field `nearby_places[].name/type/distance_km`. Lọc theo
    LMK_TYPE_KEEP (chỉ loại có giá trị du lịch/định vị: bãi biển, theme park, bảo tàng, sân bay...)
    + ngưỡng LMK_MIN_HOTELS (>=4 hotel). located_in = city xuất hiện nhiều nhất trong các hotel
    chứa landmark đó (data không có vị trí landmark trực tiếp -> suy gián tiếp, không đoán).
    Quan hệ near (hotel<->landmark+km) vẫn ở relations_near.generated.yaml (build_relations).

OUTPUT: ontology/core/location.generated.yaml (TỰ SINH — không sửa tay; chạy lại khi corpus đổi).
    location.yaml chỉ còn alias tinh chỉnh tay (nếu cần) — landmark giờ do file này sinh hết.

Mỗi concept có: facet, fact_type=hard, tier=core, kind, parent/located_in, label{vi,en},
surface_forms{vi} (tên gốc + bản không dấu để build_synonym_index nhận query), description (đếm hotel).

Chạy:  .venv/Scripts/python.exe -X utf8 -m knowledge_engineering.entity_extraction.build_locations
"""

import glob
import json
import re
from collections import Counter, defaultdict

import yaml

from knowledge_engineering.common.normalize import strip_diacritics, to_nfc

HOTELS_GLOB = "data/cleaned/hotel_*.json"
OUT_YAML = "ontology/core/location.generated.yaml"
CANDIDATES_YAML = "ontology/candidate/location_candidates.yaml"  # MỨC 3: country lạ chờ duyệt
REGISTRY_YAML = "ontology/core/location_id_registry.yaml"  # #2: ID danh tính cố định (append-only)

# Map tên country (tiếng Việt trong data) -> slug ID en. PHẠM VI VN: chỉ cần Việt Nam.
# Giữ dạng bảng (thay vì hardcode) + cơ chế auto-slug (country_slug) để nếu data lỡ có nước lạ
# thì KHÔNG kẹt (Mức 3): tự sinh + log location_candidates. Mặc định corpus thuần VN -> 1 nước.
COUNTRY_SLUG = {
    "Việt Nam": "VIETNAM",
}

# TÁCH TỈNH tự động từ tên city: "Quy Nhơn (Bình Định)" -> tỉnh "Bình Định"; "Thanh Hoá / Bãi
# biển Sầm Sơn" -> tỉnh "Thanh Hoá" (phần trước '/'). City KHÔNG có tỉnh -> parent thẳng VN.
# Trả về (province_label, city_label_thuần) hoặc (None, city gốc) nếu không tách được.
def split_province(city: str):
    c = to_nfc(city).strip()
    m = re.search(r"^(.*?)\s*\((.+?)\)\s*$", c)        # "City (Tỉnh)"
    if m:
        return m.group(2).strip(), m.group(1).strip()
    if "/" in c:                                        # "Thanh Hoá / Bãi biển Sầm Sơn"
        head, tail = c.split("/", 1)
        return head.strip(), tail.strip()
    return None, c

# ── OVERRIDE ID + QUAN HỆ (Phương án 1) ─────────────────────────────────────────
# generated slug theo tên data (Agoda kèm "Đảo/Biển/Đồng Hới") -> ID dài, lệch ID quen Sprint 1.
# Bảng dưới ÉP ID generated về ID curated + gắn `related`/`parent` curated, để:
#   (a) 1 ID duy nhất / nơi (location.yaml KHÔNG còn place — chỉ landmark),
#   (b) KHÔNG phải sửa tham chiếu ở ontology.yaml / facets.yaml / query_expansion / golden.
#
# CITY_OVERRIDE: city_slug (từ data, KHÔNG kèm tỉnh) -> {id?, related?, extra?}.
#   - id:      ép ID quen Sprint 1 (Phú Quốc, Cửa Lò...) thay vì slug mặc định.
#   - related: gắn quan hệ ngữ nghĩa (Phú Quốc -> đảo, Cửa Lò -> ven biển).
#   - extra:   cách gõ bổ sung (tên data có tiền tố "Đảo/Biển" -> thêm tên trần).
# parent (tỉnh) KHÔNG khai ở đây nữa — nay TÁCH TỰ ĐỘNG từ tên city qua split_province().
CITY_OVERRIDE = {
    "DAO_PHU_QUOC":  {"id": "LOC_PHU_QUOC", "related": ["SETTING_ISLAND"],  "extra": ["phú quốc", "đảo phú quốc"]},
    "BIEN_CUA_LO":   {"id": "LOC_CUA_LO",   "related": ["SETTING_COASTAL"], "extra": ["cửa lò", "biển cửa lò"]},
    # "Thanh Hoá / Bãi biển Sầm Sơn" -> city_clean "Bãi biển Sầm Sơn"; thêm cách gõ trần "sầm sơn".
    "BAI_BIEN_SAM_SON": {"id": "LOC_BAI_BIEN_SAM_SON", "related": ["SETTING_COASTAL"], "extra": ["sầm sơn", "bãi biển sầm sơn"]},
}

# AREA_OVERRIDE: (city_slug, area_slug từ data) -> {id, related?}. parent = id của city (đã override).
# Cho các sub-area Sprint 1 (Hòn Tre/Gành Dầu/Cửa Đại) giữ ID ngắn + related.
AREA_OVERRIDE = {
    ("NHA_TRANG", "HON_TRE"):     {"id": "LOC_HON_TRE",  "related": ["SETTING_ISLAND"]},
    ("DAO_PHU_QUOC", "GANH_DAU"): {"id": "LOC_GANH_DAU"},
    ("HOI_AN", "CUA_DAI"):        {"id": "LOC_CUA_DAI",  "related": ["SETTING_COASTAL"]},
}


def province_id(prov_label: str) -> str:
    """ID tỉnh: LOC_<slug>_TINH — hậu tố _TINH để KHÔNG bao giờ đụng ID city cùng tên."""
    return f"LOC_{slug(prov_label)}_TINH"

# ── LANDMARK (LMK_*) tự sinh từ nearby_places ───────────────────────────────────
LMK_MIN_HOTELS = 4          # chỉ sinh landmark xuất hiện ở >= 4 hotel (lọc nhiễu)

# Lọc theo `type` (Agoda, tiếng Việt) -> landmark_type (en). CHỈ giữ loại có giá trị du lịch/
# định vị; BỎ tiện ích đời thường (bệnh viện, ngân hàng, siêu thị, bãi đỗ xe, đại sứ quán...).
LMK_TYPE_KEEP = {
    "Bãi Biển": "beach",
    "Đảo": "island",
    "Vịnh": "bay",
    "Công Viên Giải Trí": "amusement_park",
    "Địa điểm giải trí": "entertainment",
    "Điểm Tham Quan": "attraction",
    "Đài Kỷ Niệm và Di Tích Lịch Sử": "historic",
    "Tòa Nhà Lịch Sử": "historic",
    "Tòa Nhà Nổi Tiếng": "landmark_building",
    "Viện Bảo Tàng và Phòng Trưng Bày Nghệ Thuật": "museum",
    "Nơi Thờ Cúng": "temple",
    "Công Viên Quốc Gia": "national_park",
    "Công Viên Công Cộng": "park",
    "Núi, đồi và hang động": "mountain",
    "Sông và Hồ": "lake",
    "Suối nước nóng và thác nước tự nhiên": "natural",
    "Vườn Bách Thảo và Vườn Thú": "zoo",
    "Phố Nổi Tiếng": "street",
    "Sân Gôn": "golf",
    "Sân Bay": "airport",
    "Bến Cảng và Bến Đò": "harbor",
    "Bến Du Thuyền": "marina",
    "Sòng Bạc": "casino",
    "Khu Nghỉ Trượt Tuyết": "ski_resort",
    "Nhà hát": "theater",
    "Nơi Biểu Diễn Văn Nghệ": "theater",
}

# #5a: BLACKLIST tên landmark GENERIC — tên chung chung (mỗi nơi 1 chỗ khác nhau bị gộp thành 1
# concept vô nghĩa). KHÔNG sinh landmark nếu tên (chuẩn hóa lower) nằm đây. KHÁC tên ngắn chính danh
# (Bãi Dài, Hòn Thơm, Núi Lê) — chúng là địa danh CỤ THỂ, vẫn giữ.
LMK_NAME_BLACKLIST = {
    "sân golf", "san golf", "nhà thi đấu", "nha thi dau", "khu vui chơi", "khu vui choi",
    "điểm ngắm cảnh", "diem ngam canh", "điểm tham quan", "diem tham quan",
    "tháp quan sát", "thap quan sat", "tháp cứu hộ", "thap cuu ho", "cầu", "cau",
    "công viên", "cong vien", "quảng trường", "quang truong", "sân vận động", "san van dong",
    "view tower", "river viewpoint", "đất 513m", "dat 513m", "the shack",
}

# Override ID cho landmark đã có ID quen (sinh phiên trước, được ontology.yaml/golden tham chiếu).
# tên data (chuẩn hóa lower) -> LMK id. Giữ để không vỡ located_in/near references.
LMK_ID_OVERRIDE = {
    "vinwonders nha trang": "LMK_VINWONDERS_NHA_TRANG",
    "vinwonders phú quốc": "LMK_VINWONDERS_PHU_QUOC",
    "vinpearl grand world phú quốc": "LMK_GRAND_WORLD_PHU_QUOC",
    "bãi dài": "LMK_BAI_DAI",
    "viện hải dương học": "LMK_VIEN_HAI_DUONG_HOC",
    "dinh bảo đại": "LMK_DINH_BAO_DAI",
}

# label EN cho country. Phạm vi VN -> chỉ cần Việt Nam. Country auto-slug (nếu có) dùng tên gốc.
COUNTRY_LABEL_EN = {
    "Việt Nam": "Vietnam",
}


def clean_text(s: str) -> str:
    """Sửa mojibake phổ biến trong data Agoda (UTF-8 đọc nhầm latin-1) trước khi đưa vào label."""
    repl = {"â€™": "'", "â€œ": '"', "â€\x9d": '"', "â€“": "-", "â€”": "-", "Â": ""}
    for a, b in repl.items():
        s = s.replace(a, b)
    return s.strip()


def slug(name: str) -> str:
    """Tên địa danh (có dấu) -> hậu tố ID: bỏ dấu, in hoa, _ thay khoảng trắng/ký tự lạ."""
    s = strip_diacritics(to_nfc(clean_text(name))).upper()
    s = re.sub(r"[^A-Z0-9]+", "_", s).strip("_")
    return s


def country_slug(co: str) -> str:
    """Slug ID của country: ưu tiên COUNTRY_SLUG (curated, ID đẹp); nếu nước lạ -> auto-slug từ tên.
    Auto-slug giúp production KHÔNG kẹt khi gặp nước mới (được log ra location_candidates để duyệt)."""
    return COUNTRY_SLUG.get(co) or slug(co)


def surface_forms(name: str) -> list[str]:
    """Các cách gõ địa danh: tên gốc + bản rút gọn (bỏ '(...)' / phần sau '/') + bản không dấu.

    Tên Agoda hay kèm tỉnh/bang trong ngoặc ("Quy Nhơn (Bình Định)", "Anaheim (CA)") hoặc ghép
    bằng '/' ("Hua Hin / Cha-am"). Người dùng gõ phần chính ("quy nhon", "anaheim", "hua hin")
    -> sinh thêm các biến thể đó để synonym khớp.
    """
    base = to_nfc(name).lower().strip()
    variants = {base}
    short = re.sub(r"\s*\(.*?\)\s*", " ", base).strip()        # bỏ "(...)"
    if short:
        variants.add(short)
    if "/" in base:                                           # "hua hin / cha-am" -> "hua hin", "cha-am"
        for part in base.split("/"):
            part = re.sub(r"\s*\(.*?\)\s*", " ", part).strip()
            if part:
                variants.add(part)
    out = set()
    for v in variants:
        out.add(v)
        out.add(strip_diacritics(v))
    return sorted(f for f in out if f)


def scan(hotels_glob: str = HOTELS_GLOB):
    """Quét data -> đếm hotel ở mỗi (country, city, area) + thu landmark từ nearby_places."""
    country_n = Counter()
    city_n = Counter()                       # key: (country, city)
    area_n = Counter()                       # key: (country, city, area)
    unknown_country = set()
    lmk_hotels = Counter()                   # landmark name -> số hotel (distinct)
    lmk_type = defaultdict(Counter)          # name -> Counter(type)
    lmk_city = defaultdict(Counter)          # name -> Counter(city hotel) để suy located_in
    city_ext = {}                            # (country, city) -> "agoda:<city_id>" (external_id ổn định)
    for f in sorted(glob.glob(hotels_glob)):
        d = json.load(open(f, encoding="utf-8"))
        co = (d.get("country") or "").strip()
        ci = (d.get("city") or d.get("province") or "").strip()
        ar = (d.get("area") or d.get("district") or "").strip()
        if not co:
            continue
        if co not in COUNTRY_SLUG:
            # MỨC 3: country lạ KHÔNG bị bỏ. Auto-slug tạm để hotel vào được NGAY, đồng thời
            # ghi nhận để log ra location_candidates.yaml cho người duyệt ID/label sau.
            unknown_country.add(co)
        country_n[co] += 1
        if ci:
            city_n[(co, ci)] += 1
            cid_agoda = d.get("city_id")
            if cid_agoda is not None and (co, ci) not in city_ext:
                city_ext[(co, ci)] = f"agoda:{cid_agoda}"   # external_id (#2 ID ổn định)
            if ar and ar != ci:              # bỏ area trùng tên city (vô nghĩa)
                area_n[(co, ci, ar)] += 1
        # landmark: gom theo tên, đếm distinct hotel + type + city của hotel chứa nó
        seen = set()
        for p in (d.get("nearby_places") or []):
            nm = (p.get("name") or "").strip()
            ty = (p.get("type") or "").strip()
            if not nm or ty not in LMK_TYPE_KEEP or nm in seen:
                continue
            if to_nfc(nm).lower().strip() in LMK_NAME_BLACKLIST:    # #5a: bỏ tên generic
                continue
            seen.add(nm)
            lmk_hotels[nm] += 1
            lmk_type[nm][ty] += 1
            if ci:
                lmk_city[nm][ci] += 1
    landmarks = (lmk_hotels, lmk_type, lmk_city)
    return country_n, city_n, area_n, unknown_country, landmarks, city_ext


def concept_block(cid, kind, label_vi, label_en, parent, sf, desc, related=None) -> str:
    lines = [
        f"  {cid}:",
        f"    facet: location",
        f"    fact_type: hard",
        f"    tier: core",
        f"    kind: {kind}",
    ]
    if parent:
        lines.append(f"    parent: {parent}")
    if related:
        lines.append(f"    related: [{', '.join(related)}]")
    lines += [
        f"    label: {{vi: {yq(label_vi)}, en: {yq(label_en)}}}",
        f"    surface_forms:",
        f"      vi: [{', '.join(yq(s) for s in sf)}]",
        f"    description: {{vi: {yq(desc)}, en: {yq(desc)}}}",
    ]
    return "\n".join(lines)


def landmark_block(cid, label, located_in, landmark_type, sf, desc) -> str:
    """Block YAML cho landmark (kind=landmark, located_in + landmark_type)."""
    lines = [
        f"  {cid}:",
        f"    facet: location",
        f"    fact_type: hard",
        f"    tier: core",
        f"    kind: landmark",
        f"    landmark_type: {landmark_type}",
        f"    provenance: [agoda]",
    ]
    if located_in:
        lines.append(f"    located_in: {located_in}")
    lines += [
        f"    label: {{vi: {yq(label)}, en: {yq(label)}}}",
        f"    surface_forms:",
        f"      vi: [{', '.join(yq(s) for s in sf)}]",
        f"    description: {{vi: {yq(desc)}, en: {yq(desc)}}}",
    ]
    return "\n".join(lines)


def yq(s: str) -> str:
    """Quote YAML an toàn cho chuỗi có dấu/ký tự đặc biệt."""
    s = str(s).replace('"', "'")
    return f'"{s}"'


class IdRegistry:
    """#2 ID ổn định — danh tính LOC_* CỐ ĐỊNH, độc lập text Agoda. APPEND-ONLY.

    resolve() 3 tầng (theo mô hình hybrid đã chốt):
      1. external_id (Agoda city_id)  -> ID đã gắn external đó (bền nhất; dù text đổi).
      2. alias/slug (tên chuẩn hóa)   -> ID đã từng thấy tên này.
      3. không khớp -> CẤP ID mới (proposed_id) + ghi registry + đánh dấu 'new' để log review.
    Mỗi lần thấy 1 concept, bổ sung alias/external mới vào entry (registry giàu dần, không mất ID).
    """

    def __init__(self, path: str = REGISTRY_YAML):
        self.path = path
        try:
            data = yaml.safe_load(open(path, encoding="utf-8")) or {}
            self.reg = data.get("registry", {}) or {}
        except FileNotFoundError:
            self.reg = {}
        # index ngược: external_id -> cid ; (kind, alias) -> cid. Alias PHẢI theo kind để
        # "thuận an" (area) KHÔNG resolve nhầm sang city LOC_THUAN_AN cùng tên khác kind.
        self.ext_index = {}
        self.alias_index = {}
        for cid, e in self.reg.items():
            k = e.get("kind")
            ctx = e.get("context", "")     # parent id (phân biệt area/landmark trùng tên giữa nơi)
            for x in e.get("external_ids", []) or []:
                self.ext_index[x] = cid
            for a in e.get("aliases", []) or []:
                self.alias_index[(k, ctx, a)] = cid
        self.newly_assigned = []   # [(cid, label)] để log

    def resolve(self, kind: str, label: str, proposed_id: str, external_id=None, context="") -> str:
        # context = parent id; đưa vào khóa để "Trung tâm thành phố" ở 2 city KHÁC không gộp nhầm.
        alias = to_nfc(label).lower().strip()
        cid = None
        if external_id and external_id in self.ext_index:        # tầng 1
            cid = self.ext_index[external_id]
        elif (kind, context, alias) in self.alias_index:         # tầng 2 (alias theo kind + ngữ cảnh cha)
            cid = self.alias_index[(kind, context, alias)]
        if cid is None:                                          # tầng 3: cấp mới
            cid = proposed_id
            self.newly_assigned.append((cid, label))
        # cập nhật entry (giàu dần) — không bao giờ đổi cid
        e = self.reg.setdefault(cid, {"kind": kind, "aliases": []})
        if context and not e.get("context"):
            e["context"] = context
        if alias not in e.get("aliases", []):
            e.setdefault("aliases", []).append(alias)
            e["aliases"] = sorted(e["aliases"])
            self.alias_index[(kind, context, alias)] = cid
        if external_id:
            exs = e.setdefault("external_ids", [])
            if external_id not in exs:
                exs.append(external_id)
                exs.sort()
                self.ext_index[external_id] = cid
        return cid

    def save(self):
        header = (
            "# ontology/core/location_id_registry.yaml — REGISTRY DANH TÍNH ID location (#2 ID ổn định).\n"
            "# ID nội bộ (LOC_*) CỐ ĐỊNH, KHÔNG đổi dù Agoda đổi text. resolve 3 tầng:\n"
            "#   (1) external_id (Agoda city_id) -> (2) alias/slug -> (3) cấp mới + log review.\n"
            "# APPEND-ONLY: ID đã cấp không xóa/đổi. Thêm alias TAY khi tên nguồn đổi hoàn toàn.\n"
            "# external_ids KHÔNG dùng làm ontology ID (tránh phụ thuộc nguồn; hỗ trợ đa nguồn sau).\n"
        )
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write(header)
            yaml.safe_dump({"registry": self.reg}, fh, allow_unicode=True, sort_keys=True)


def build(hotels_glob: str = HOTELS_GLOB) -> str:
    country_n, city_n, area_n, unknown, landmarks, city_ext = scan(hotels_glob)
    reg = IdRegistry()

    # Tách tỉnh từ tên city (split_province). city_clean = label city thuần (bỏ phần tỉnh).
    # prov_of[(co,ci)] = (province_id, province_label) hoặc None.
    prov_of = {}
    city_clean = {}
    for (co, ci) in city_n:
        plabel, cclean = split_province(ci)
        city_clean[(co, ci)] = cclean
        prov_of[(co, ci)] = (province_id(plabel), plabel) if (co == "Việt Nam" and plabel) else None

    # CITY-STATE: city trùng slug với chính country (Singapore/HK...) -> gắn thẳng country.
    country_slugs = {f"LOC_{country_slug(co)}" for co in country_n}
    city_state = {(co, ci) for (co, ci) in city_n
                  if f"LOC_{slug(city_clean[(co, ci)])}" == f"LOC_{country_slug(co)}"}

    # CITY == PROVINCE: data bẩn — hotel ghi city = TÊN TỈNH (vd city "Phú Thọ" trong khi
    # hotel khác có "Việt Trì (Phú Thọ)" -> đã tạo province LOC_PHU_THO_TINH). City trần đó
    # trùng tỉnh -> KHÔNG tạo concept city riêng (tránh LOC_PHU_THO ≡ LOC_PHU_THO_TINH trùng),
    # mà gắn thẳng vào province (coi như "trung tâm tỉnh").
    province_label_slugs = {slug(pv[1]) for pv in prov_of.values() if pv}  # slug các tỉnh đã tách
    city_is_province = {(co, ci) for (co, ci) in city_n
                        if prov_of[(co, ci)] is None
                        and slug(city_clean[(co, ci)]) in province_label_slugs}

    # ID city: proposed = CITY_OVERRIDE (ID quen) > slug (tránh trùng). Sau đó qua REGISTRY resolve
    # (external_id Agoda city_id -> alias -> proposed) để ID CỐ ĐỊNH dù Agoda đổi text tên.
    city_id = {}
    seen_city_slug = Counter()
    for (co, ci), n in sorted(city_n.items(), key=lambda x: (-x[1], x[0])):
        if (co, ci) in city_state:
            city_id[(co, ci)] = f"LOC_{country_slug(co)}"
            continue
        if (co, ci) in city_is_province:
            # city trần == tên tỉnh -> dùng luôn province_id (không tạo concept city trùng)
            city_id[(co, ci)] = province_id(city_clean[(co, ci)])
            continue
        cc = city_clean[(co, ci)]
        if slug(cc) in CITY_OVERRIDE:
            proposed = CITY_OVERRIDE[slug(cc)]["id"]
        else:
            base = slug(cc)
            proposed = f"LOC_{base}"
            seen_city_slug[base] += 1
            if seen_city_slug[base] > 1 or proposed in country_slugs:
                proposed = f"LOC_{country_slug(co)}_{base}"
        city_id[(co, ci)] = reg.resolve("place", cc, proposed, external_id=city_ext.get((co, ci)))

    def city_parent(co, ci):
        """parent city = tỉnh (nếu tách được từ tên) > country."""
        p = prov_of[(co, ci)]
        return p[0] if p else f"LOC_{country_slug(co)}"

    out = []
    out.append("# ontology/core/location.generated.yaml — TỰ SINH bởi build_locations.py (Lớp A).")
    out.append("# KHÔNG sửa tay. Nguồn: data/cleaned/*.json (field country/city/area). PHẠM VI: Việt Nam.")
    out.append("# Cây: country > province > city > area. Landmark (LMK_*) cũng sinh ở đây.")
    out.append(f"# Thống kê: {sum(country_n.values())} hotel / {len(country_n)} country / "
               f"{len(city_n)} city / {len(area_n)} area.")
    if unknown:
        out.append(f"# ⚠ Country auto-slug (ngoài VN, chờ duyệt -> location_candidates): {sorted(unknown)}")
    out.append("")
    out.append("concepts:")
    out.append("")

    # 1) COUNTRY
    out.append("  # ===== COUNTRY (kind: country) =====")
    for co, n in sorted(country_n.items(), key=lambda x: (-x[1], x[0])):
        cid = reg.resolve("country", co, f"LOC_{country_slug(co)}")
        label_en = COUNTRY_LABEL_EN.get(co, co)
        out.append(concept_block(cid, "country", co, label_en, None,
                                 surface_forms(co), f"{co} ({n} hotel trong corpus)"))
        out.append("")

    # 2) PROVINCE — tách TỰ ĐỘNG từ tên city "City (Tỉnh)". parent = country.
    used_provinces = {}   # province_id -> (label, country)
    for (co, ci) in city_n:
        if (co, ci) in city_state:
            continue
        p = prov_of[(co, ci)]
        if p:
            used_provinces[p[0]] = (p[1], co)
    if used_provinces:
        out.append("  # ===== PROVINCE (kind: place) — TÁCH tự động từ 'City (Tỉnh)' trong data =====")
        for pid, (plabel, co) in sorted(used_provinces.items()):
            rid = reg.resolve("place", plabel, pid)
            out.append(concept_block(rid, "place", plabel, plabel, f"LOC_{country_slug(co)}",
                                     surface_forms(plabel), f"Tỉnh {plabel}, {co}"))
            out.append("")

    # 3) CITY (parent = province/country). ID + related có thể bị CITY_OVERRIDE ép. label = city thuần.
    out.append("  # ===== CITY (kind: place) =====")
    out.append("  # (ID/related vài nơi ép theo CITY_OVERRIDE để khớp ID quen: Phú Quốc, Cửa Lò...)")
    for (co, ci), n in sorted(city_n.items(), key=lambda x: (-x[1], x[0])):
        if (co, ci) in city_state:
            continue
        if (co, ci) in city_is_province:
            continue   # city trần == tỉnh -> đã trỏ vào province block, không tạo block city trùng
        cid = city_id[(co, ci)]
        cc = city_clean[(co, ci)]
        ov = CITY_OVERRIDE.get(slug(cc), {})
        sf = surface_forms(cc)
        for ex in ov.get("extra", []):                    # thêm cách gõ trần (bỏ tiền tố Đảo/Biển)
            sf += [s for s in surface_forms(ex) if s not in sf]
        out.append(concept_block(cid, "place", cc, cc, city_parent(co, ci),
                                 sf, f"{cc}, {co} ({n} hotel)", related=ov.get("related")))
        out.append("")

    # 4) AREA (parent = city). ID + related có thể bị AREA_OVERRIDE ép (sub-area Sprint 1).
    out.append("  # ===== AREA (kind: area) — gộp district (area==district trong data) =====")
    out.append("  # (ID vài sub-area ép theo AREA_OVERRIDE để khớp ID quen: Hòn Tre, Gành Dầu, Cửa Đại)")
    for (co, ci, ar), n in sorted(area_n.items(), key=lambda x: (-x[1], x[0])):
        parent = city_id[(co, ci)]
        ov = AREA_OVERRIDE.get((slug(city_clean[(co, ci)]), slug(ar)))
        if ov:
            proposed = ov["id"]
            related = ov.get("related")
        else:
            proposed = f"{parent}__{slug(ar)}"   # area id = <city_id>__<area_slug> tránh trùng toàn cục
            related = None
        cid = reg.resolve("area", ar, proposed, context=parent)   # context=city -> area trùng tên khác city không gộp
        out.append(concept_block(cid, "area", ar, ar, parent,
                                 surface_forms(ar), f"{ar} (thuộc {ci}, {co}; {n} hotel)", related=related))
        out.append("")

    # 5) LANDMARK (kind: landmark) — tự sinh từ nearby_places. located_in = city nhiều nhất.
    lmk_hotels, lmk_type, lmk_city = landmarks
    out.append("  # ===== LANDMARK (kind: landmark) — TỰ SINH từ nearby_places (>=%d hotel) =====" % LMK_MIN_HOTELS)
    out.append("  # located_in = city xuất hiện nhiều nhất; landmark_type map từ `type` Agoda.")
    out.append("  # ID vài landmark ép theo LMK_ID_OVERRIDE để khớp ID quen (VinWonders, Bãi Dài...).")
    seen_lmk_id = {}      # id -> name (chống trùng ID)
    lmk_list = sorted(
        ((nm, c) for nm, c in lmk_hotels.items() if c >= LMK_MIN_HOTELS),
        key=lambda x: (-x[1], x[0]),
    )
    for nm, n in lmk_list:
        low = to_nfc(nm).lower().strip()
        # located_in = city có NHIỀU hotel chứa landmark nhất. #4: tie-break TẤT ĐỊNH khi bằng điểm
        # (sort theo (-count, tên city) -> alphabet) để located_in KHÔNG dao động giữa các lần chạy.
        top_city = (sorted(lmk_city[nm].items(), key=lambda x: (-x[1], x[0]))[0][0]
                    if lmk_city[nm] else None)
        loc_in = None
        for (co, ci), cidv in city_id.items():
            if ci == top_city:
                loc_in = cidv
                break
        # proposed ID: override > LMK_<slug>; đụng -> thêm slug city. Rồi qua REGISTRY (alias) để cố định.
        if low in LMK_ID_OVERRIDE:
            proposed = LMK_ID_OVERRIDE[low]
        else:
            proposed = f"LMK_{slug(nm)}"
            if proposed in seen_lmk_id:
                proposed = f"LMK_{slug(nm)}_{slug(top_city or '')}".rstrip("_")
        cid = reg.resolve("landmark", nm, proposed, context=(loc_in or ""))
        if cid in seen_lmk_id:        # vẫn đụng (cùng tên) -> bỏ qua bản sau
            continue
        seen_lmk_id[cid] = nm
        ltype = LMK_TYPE_KEEP[lmk_type[nm].most_common(1)[0][0]]
        # sân bay phục vụ cả VÙNG (xuất hiện rải nhiều tỉnh) -> "city max" vô nghĩa, BỎ located_in.
        # Quan hệ near (hotel<->sân bay+km) vẫn ở relations_near là đủ cho "gần sân bay".
        if ltype == "airport":
            loc_in = None
        label = clean_text(nm)
        out.append(landmark_block(cid, label, loc_in, ltype, surface_forms(nm),
                                  f"{label} ({n} hotel có trong nearby)"))
        out.append("")

    reg.save()                       # lưu registry (append-only, đã giàu thêm alias/external mới)
    build.last_registry = reg        # để main() đọc số liệu (new assigned)
    return "\n".join(out).rstrip() + "\n"


def write_candidates(country_n, unknown, out_yaml: str = CANDIDATES_YAML) -> int:
    """MỨC 3: ghi country lạ (auto-slug) ra hàng đợi duyệt. Hotel của chúng ĐÃ vào ontology
    (auto-slug), đây chỉ là việc CHỜ NGƯỜI xác nhận/đặt ID-label đẹp, KHÔNG chặn luồng.
    File luôn được ghi (kể cả rỗng) để trạng thái rõ ràng. Trả số candidate."""
    items = []
    for co in sorted(unknown):
        items.append({
            "country_name": co,                          # tên thô trong data
            "auto_id": f"LOC_{slug(co)}",                # ID tạm script đã sinh (đang dùng thật)
            "hotel_count": country_n.get(co, 0),
            "status": "pending",                         # pending -> approved (thêm vào COUNTRY_SLUG)
            "action": "Xác nhận/sửa slug ID + label EN rồi thêm vào COUNTRY_SLUG/COUNTRY_LABEL_EN trong build_locations.py",
        })
    header = (
        "# ontology/candidate/location_candidates.yaml — AUTO-GENERATED bởi build_locations.py.\n"
        "# MỨC 3 (production-safe): country MỚI chưa có trong COUNTRY_SLUG được auto-slug để hotel\n"
        "# vào ontology NGAY (không chặn luồng nạp dữ liệu). Mục dưới CHỜ NGƯỜI duyệt: xác nhận/đổi\n"
        "# slug ID đẹp + label EN, rồi thêm vào COUNTRY_SLUG trong build_locations.py và chạy lại.\n"
        "# Đây KHÁC candidate_queue.yaml (concept ngữ nghĩa từ review). Location = data-driven, auto-OK.\n"
        "# status: pending | approved.\n"
    )
    with open(out_yaml, "w", encoding="utf-8") as fh:
        fh.write(header)
        yaml.safe_dump({"location_candidates": items}, fh, allow_unicode=True, sort_keys=False)
    return len(items)


def main():
    text = build()
    with open(OUT_YAML, "w", encoding="utf-8") as fh:
        fh.write(text)
    country_n, city_n, area_n, unknown, landmarks, _ = scan()
    n_cand = write_candidates(country_n, unknown)
    n_lmk = sum(1 for c in landmarks[0].values() if c >= LMK_MIN_HOTELS)
    reg = getattr(build, "last_registry", None)
    print(f"Đã ghi {OUT_YAML}")
    print(f"  country={len(country_n)}  city={len(city_n)}  area={len(area_n)}  "
          f"landmark={n_lmk} (>={LMK_MIN_HOTELS} hotel)  "
          f"(hotel có country={sum(country_n.values())})")
    if reg is not None:
        new = reg.newly_assigned
        print(f"  registry: {len(reg.reg)} ID cố định -> {REGISTRY_YAML}"
              + (f"  | {len(new)} ID MỚI cấp: {[c for c, _ in new][:8]}" if new else "  | 0 ID mới (khớp hết)"))
    if unknown:
        print(f"  ⚠ {len(unknown)} country auto-slug (chờ duyệt ID đẹp) -> {CANDIDATES_YAML}: {sorted(unknown)}")
    else:
        print(f"  ✓ mọi country đã có trong COUNTRY_SLUG (0 candidate)")


if __name__ == "__main__":
    main()
