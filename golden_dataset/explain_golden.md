# Giải thích Golden Set v1 — Search API Evaluation

Tài liệu mô tả **50 query** trong `golden_set_v1.json` theo cách dễ đọc: nội dung query, mục đích kiểm tra, và kết quả mong đợi.

**Nguồn dữ liệu:** 520 hotels từ `data/` → `evaluation/corpus/hotel_corpus.jsonl`, `faq_activities_corpus.jsonl`, `policies_corpus.jsonl`

**Labeler:** Kiên | **Version:** v1

---

## Tổng quan

| Metric | Giá trị |
|--------|---------|
| Tổng query | 50 |
| Nhóm | 5 (mỗi nhóm 10 query) |
| Intent | Tất cả là `hotel_search` (tìm KS/resort) |
| top_k đánh giá | 5 (GS-ACT-008 chỉ có 4 KS thoả) |

### 5 nhóm theo NGUỒN chứa câu trả lời

| Nhóm | Prefix | Nguồn dữ liệu | Ý nghĩa |
|------|--------|---------------|---------|
| Description | GS-DESC-* | `description`, `useful_info` | Thông tin narrative — **không suy ra từ amenities** |
| FAQ | GS-FAQ-* | Trường `faq` | Câu hỏi-đáp về tiện nghi, chính sách, giá... |
| Activities | GS-ACT-* | Trường `activities` | Tour, vé, trải nghiệm book qua KS |
| Policies | GS-POL-* | `secondary.hotel_policy.policyNotes` | Chính sách trẻ em, giường phụ, giấy tờ... |
| Amenities | GS-AMEN-* | Trường `amenities` | Tag tiện nghi chuẩn hóa |

### Cách đọc Expected outcome

- `relevant_hotel_ids` là **danh sách tên KS** (chưa map sang `hotels.id`), **sắp xếp giảm dần theo độ liên quan**.
- Kết quả Search API top 5 nên **khớp hoặc gần khớp** thứ tự ground truth.
- Nhóm FAQ/ACT/POL/AMEN đều **nêu rõ city** trong query.
- Nhóm POL/AMEN: xếp hạng ground truth theo `review_score` giảm dần trong số KS thoả điều kiện.

---

## Mục lục

1. [GS-DESC — Description (1–10)](#gs-desc--description-110)
2. [GS-FAQ — FAQ (1–10)](#gs-faq--faq-110)
3. [GS-ACT — Activities (1–10)](#gs-act--activities-110)
4. [GS-POL — Policies (1–10)](#gs-pol--policies-110)
5. [GS-AMEN — Amenities (1–10)](#gs-amen--amenities-110)

---

## GS-DESC — Description (1–10)

**Mục đích nhóm:** Kiểm tra retrieval hiểu nội dung **mô tả narrative** trong description — thông tin không có trong tag amenities (vị trí đặc biệt, phong cách, cảm nhận không gian...).

---

### GS-DESC-001 — Khách sạn mới xây dựng

**Nội dung query:**
```
Tìm khách sạn mới xây dựng gần đây, cơ sở vật chất còn mới
```

**Mục đích test:**
- Retrieval từ **description/useful_info** về năm xây dựng, KS mới khai trương.
- Không thể suy ra từ amenities tag.

**Expected outcome:**
- Intent: `hotel_search`
- Top 5 KS liên quan (theo thứ tự giảm dần):
  1. Khách sạn Sala Quy Nhơn Beach
  2. Khách sạn Công Tử Bạc Liêu
  3. Four Points by Sheraton Hà Giang
  4. Khách sạn Pullman Grand Hải Phòng
  5. Khách sạn Golden Sun Đà Lạt
- Xếp hạng ưu tiên năm mới (2025 > 2024) rồi `review_score`

---

### GS-DESC-002 — Resort trên đảo, biệt lập

**Nội dung query:**
```
Tìm resort nằm trên đảo, không gian biệt lập hoang sơ tách biệt
```

**Hard filter:** `accommodation_type` = Resort

**Mục đích test:**
- Mô tả vị trí "trên đảo", "biệt lập", "hoang sơ" trong description (ví dụ Hòn Tre).
- Không phải tag amenities.

**Expected outcome:**
- Top 5:
  1. JW Marriott Phu Quoc Emerald Bay Resort & Spa
  2. Vinpearl Resort Nha Trang
  3. The Secret Con Dao
  4. Khu nghỉ dưỡng Flamingo Cát Bà
  5. Khu nghỉ dưỡng & Spa Lahana Phú Quốc

---

### GS-DESC-003 — KS trong phố cổ Hội An

**Nội dung query:**
```
Tìm khách sạn nằm ngay trong khu phố cổ Hội An
```

**Hard filter:** `city` = Hội An

**Mục đích test:**
- Vị trí "ngay trung tâm phố cổ" trong description, không phải amenities.

**Expected outcome:**
- Top 5:
  1. Khách sạn Hoianese Quiet Old Town
  2. Nam An Mama Villa Hội An
  3. Khách sạn Hoianan Boutique
  4. Khách sạn & Spa Happy Life Memories Hội An
  5. Khách sạn Gia Huy Riverside Hội An
- 3 đầu gần lõi phố cổ hơn 2 sau

---

### GS-DESC-004 — KS ven sông, view sông

**Nội dung query:**
```
Tìm khách sạn nằm ngay bên bờ sông, view sông thơ mộng
```

**Mục đích test:**
- Vị trí "ngay bên bờ sông" (sông Hàn, Sài Gòn, sông Hậu...) chỉ có trong description.

**Expected outcome:**
- Top 5:
  1. Khách sạn Bamboo Riverside Boutique
  2. Khách sạn Lá Riverside Boutique
  3. Novotel Đà Nẵng Premier Han River
  4. Khách sạn Renaissance Riverside Sài Gòn
  5. Saigon River Hotel - Quận 2

---

### GS-DESC-005 — KS boutique ấm cúng

**Nội dung query:**
```
Tìm khách sạn phong cách boutique nhỏ xinh ấm cúng
```

**Mục đích test:**
- Phong cách "boutique / ấm cúng" là cảm nhận trong description, không có tag amenities.

**Expected outcome:**
- Top 5:
  1. Khách sạn Hoianese Quiet Old Town
  2. Charmant Suites a Boutique Hotel Cần Thơ
  3. Khách sạn Hoianan Boutique
  4. Khách sạn Bamboo Riverside Boutique
  5. Khách sạn Lá Riverside Boutique

---

### GS-DESC-006 — KS gần sân bay

**Nội dung query:**
```
Tìm khách sạn gần sân bay, chỉ mất vài phút di chuyển
```

**Mục đích test:**
- Khoảng cách cụ thể tới sân bay ("5/10/15 phút") trong description/useful_info, không trong amenities.

**Expected outcome:**
- Top 5:
  1. Novotel Đà Nẵng Premier Han River
  2. Khách sạn Mường Thanh Grand Đà Nẵng
  3. Melia Vinpearl Quảng Bình
  4. Khu nghỉ dưỡng & Biệt thự Rosa Alba Tuy Hòa
  5. Mercure Hải Phòng
- Xếp theo khoảng cách tăng dần rồi `review_score`

---

### GS-DESC-007 — Resort khu vườn nhiệt đới

**Nội dung query:**
```
Tìm resort có khu vườn xanh nhiệt đới rộng rãi để thư giãn
```

**Mục đích test:**
- Quy mô/đặc tính "khu vườn nhiệt đới rộng" trong description; amenities không mô tả chi tiết.

**Expected outcome:**
- Top 5:
  1. Khách sạn Radisson Blu Vịnh Hạ Long
  2. Khu nghỉ dưỡng Holiday Inn Hồ Tràm Beach By IHG
  3. Radisson Resort Phan Thiết
  4. The Nam An Villa Hoi An
  5. Hòa Bình Rạch Giá Resort

---

### GS-DESC-008 — Ngắm bình minh/hoàng hôn biển

**Nội dung query:**
```
Tìm khách sạn ngắm được bình minh hoặc hoàng hôn trên biển
```

**Mục đích test:**
- Trải nghiệm ngắm bình minh/hoàng hôn từ phòng/vị trí KS — narrative trong description.

**Expected outcome:**
- Top 5:
  1. Khách sạn PLUS Vũng Tàu
  2. Khách sạn LyTri Lý Sơn
  3. Apec Tuy Hòa SeaView Condotel
  4. Vinpearl Resort & Spa Hạ Long
  5. FLC Quy Nhơn Sea Condotel
- Ưu tiên KS nói rõ ngắm từ chính phòng/vị trí KS

---

### GS-DESC-009 — KS cao nguyên đồi núi

**Nội dung query:**
```
Tìm khách sạn trên vùng cao nguyên đồi núi, không khí trong lành
```

**Mục đích test:**
- Bối cảnh "cao nguyên / trên đồi nhìn thung lũng" trong description.

**Expected outcome:**
- Top 5:
  1. Plum Village Mộc Châu
  2. Khách sạn Glenda Tower Mộc Châu
  3. Khu nghỉ dưỡng và công viên núi Đảo Mộc Châu
  4. Hôtel de l'Amour Tam Đảo
  5. Four Points by Sheraton Hà Giang

---

### GS-DESC-010 — Resort yên tĩnh tách biệt

**Nội dung query:**
```
Tìm resort yên tĩnh tách biệt khỏi ồn ào phố thị để nghỉ dưỡng
```

**Mục đích test:**
- Cảm nhận "yên tĩnh, tách biệt khỏi ồn ào" — narrative description, không suy từ amenities.

**Expected outcome:**
- Top 5:
  1. Four Seasons Resort The Nam Hai Hoi An Vietnam
  2. JW Marriott Phu Quoc Emerald Bay Resort & Spa
  3. Resort Thiên Thanh
  4. FLC Luxury Hotel Quy Nhơn
  5. Khu nghỉ dưỡng & Spa Lahana Phú Quốc

---

## GS-FAQ — FAQ (1–10)

**Mục đích nhóm:** Kiểm tra retrieval tìm câu trả lời trong trường **faq** — thông tin chi tiết về tiện nghi, thanh toán, chính sách gia đình, giá... mà amenities không có.

Tất cả query đều nêu rõ **city**. Ground truth xếp theo `review_score` giảm dần.

---

### GS-FAQ-001 — Bãi đỗ xe Nha Trang

**Nội dung query:**
```
Tìm khách sạn ở Nha Trang có bãi đỗ xe cho khách
```
- Hard filter: `city` = Nha Trang

**Mục đích test:** FAQ category `hotel_facilities_parking`

**Expected outcome — Top 5:**
1. Sunrise Nha Trang Beach Hotel & Spa
2. Vinpearl Beachfront Nha Trang
3. Muong Thanh Luxury Viễn Triều Nha Trang
4. Lucky Sun Hotel
5. Liberty Central Nha Trang

---

### GS-FAQ-002 — Giặt là Hà Nội

**Nội dung query:**
```
Tìm khách sạn ở Hà Nội có dịch vụ giặt là, giặt khô
```
- Hard filter: `city` = Hà Nội

**Mục đích test:** FAQ category `hotel_facilities_cleaning`

**Expected outcome — Top 5:**
1. Novotel Suites Hà Nội
2. A25 Hotel - 96 Hai Bà Trưng
3. Novotel Hà Nội Thái Hà
4. Minasi HanoiOi LakeSide Hotel
5. A25 Hotel - 46 Châu Long

---

### GS-FAQ-003 — Thanh toán thẻ Hồ Chí Minh

**Nội dung query:**
```
Tìm khách sạn ở Hồ Chí Minh chấp nhận thanh toán bằng thẻ Visa, MasterCard
```
- Hard filter: `city` = Hồ Chí Minh

**Mục đích test:** FAQ category `property_info_payment`

**Expected outcome — Top 5:**
1. Express by M Village Điện Biên Phủ (The Tropic)
2. Sofitel Saigon Plaza Hotel
3. ibis Saigon Airport
4. A25 Hotel - 307 Lý Tự Trọng
5. Cochin Zen Hotel

---

### GS-FAQ-004 — Đưa đón sân bay Hội An

**Nội dung query:**
```
Tìm khách sạn ở Hội An có dịch vụ đưa đón sân bay
```
- Hard filter: `city` = Hội An

**Mục đích test:** FAQ về shuttle sân bay (theo yêu cầu, phụ thu...)

**Expected outcome — Top 5:**
1. Sunora Villa Hội An
2. Gia Huy Riverside Hotel Hoi An
3. Wyndham Garden Hoi An Cua Dai Beach
4. Nam An Mama Villa Hoi An
5. Hoi An Dream City Hotel

---

### GS-FAQ-005 — Bể bơi Hồ Chí Minh

**Nội dung query:**
```
Tìm khách sạn ở Hồ Chí Minh có bể bơi
```
- Hard filter: `city` = Hồ Chí Minh

**Mục đích test:** FAQ category `hotel_facilities_things-to-do`

**Expected outcome — Top 5:**
1. Vinpearl Landmark 81, Autograph Collection
2. Sheraton Saigon Grand Opera Hotel
3. Liberty Central Saigon Citypoint Hotel
4. ibis Saigon Airport
5. Liberty Central Saigon Riverside Hotel

---

### GS-FAQ-006 — Quán bar Đà Nẵng

**Nội dung query:**
```
Tìm khách sạn ở Đà Nẵng có quán bar trong khuôn viên
```
- Hard filter: `city` = Đà Nẵng

**Mục đích test:** FAQ category `hotel_facilities_food and drink`

**Expected outcome — Top 5:**
1. Pullman Danang Beach Resort
2. Novotel Danang Premier Han River
3. Mercure Danang French Village Bana Hills
4. Sunshine Beach Da Nang
5. Orange City Center Hotel Da Nang

---

### GS-FAQ-007 — Gia đình có trẻ em Hà Nội

**Nội dung query:**
```
Tìm khách sạn ở Hà Nội phù hợp cho gia đình có trẻ em
```
- Hard filter: `city` = Hà Nội, `suitable_for` = Gia đình có trẻ nhỏ

**Mục đích test:** FAQ category `property_policies_family` (giường ngủ, độ tuổi trẻ em)

**Expected outcome — Top 5:**
1. Minasi Grand Hotel
2. Sheraton Hanoi West
3. Wyndham Garden Hanoi
4. A25 Hotel - 96 Hai Bà Trưng
5. A25 Hotel - 46 Châu Long

---

### GS-FAQ-008 — Giá phòng trung bình Nha Trang

**Nội dung query:**
```
Tìm khách sạn ở Nha Trang có mức giá phòng trung bình hợp lý
```
- Hard filter: `city` = Nha Trang

**Mục đích test:** FAQ category `property_info_price` — giá TB so với thành phố

**Expected outcome — Top 5:**
1. Vinpearl Luxury Nha Trang
2. The Westin Resort & Spa Cam Ranh
3. Vinpearl Beachfront Nha Trang
4. Muong Thanh Luxury Khanh Hoa
5. Muong Thanh Luxury Vien Trieu Nha Trang

---

### GS-FAQ-009 — Năm xây dựng Hồ Chí Minh

**Nội dung query:**
```
Tìm khách sạn ở Hồ Chí Minh được xây dựng từ năm nào
```
- Hard filter: `city` = Hồ Chí Minh

**Mục đích test:** FAQ category `property_info_property`

**Expected outcome — Top 5:**
1. JW Marriott Hotel & Suites Saigon
2. ibis Saigon Airport
3. Pullman Saigon Centre Hotel
4. Liberty Central Saigon Riverside Hotel
5. Novotel Saigon Centre Hotel

---

### GS-FAQ-010 — Nhân viên nói tiếng Anh Hạ Long

**Nội dung query:**
```
Tìm khách sạn ở Hạ Long có nhân viên nói được tiếng Anh
```
- Hard filter: `city` = Hạ Long

**Mục đích test:** FAQ category `property_info_languages spoken`

**Expected outcome — Top 5:**
1. Green bay hotel Ha Long
2. Halong Boutique Hotel
3. Wyndham Legend Halong Hotel
4. Muong Thanh Holiday Suoi Mo
5. Halios Halong Hotel

---

## GS-ACT — Activities (1–10)

**Mục đích nhóm:** Kiểm tra retrieval tìm **activities** — tour, vé, trải nghiệm có thể đặt qua KS.

Ground truth xếp theo **số activity khớp** rồi `review_score`.

---

### GS-ACT-001 — VinWonders Nha Trang

**Nội dung query:**
```
Tìm khách sạn ở Nha Trang có thể đặt vé VinWonders, công viên giải trí Vinpearl
```
- Hard filter: `city` = Nha Trang

**Mục đích test:** Activities VinWonders / Vinpearl Harbour

**Expected outcome — Top 5:**
1. Muong Thanh Luxury Khanh Hoa
2. Liberty Central Nha Trang
3. TTC Hotel - Michelia
4. Wyndham Garden Cam Ranh Resort
5. Muong Thanh Grand Nha Trang Hotel

---

### GS-ACT-002 — Du thuyền vịnh Hạ Long

**Nội dung query:**
```
Tìm khách sạn ở Hạ Long có thể đặt tour du thuyền tham quan vịnh
```
- Hard filter: `city` = Hạ Long

**Mục đích test:** Activities cruise vịnh Hạ Long

**Expected outcome — Top 5:**
1. Vinpearl Resort & Spa Ha Long
2. Muong Thanh Grand Bai Chay
3. Muong Thanh Holiday Suoi Mo
4. Muong Thanh Luxury Ha Long Centre II
5. Muong Thanh Grand Ha Long Hotel

---

### GS-ACT-003 — Cáp treo Bà Nà Hills Đà Nẵng

**Nội dung query:**
```
Tìm khách sạn ở Đà Nẵng có thể đặt vé cáp treo Bà Nà Hills, Sun World
```
- Hard filter: `city` = Đà Nẵng

**Mục đích test:** Activities Sun World Bà Nà / cáp treo

**Expected outcome — Top 5:**
1. Wyndham Soleil Danang
2. Ocean Star Da Nang Bay Hotel
3. Cherry Hotel Da Nang
4. Orange City Center Hotel Da Nang
5. Moonlight Hotel Da Nang

---

### GS-ACT-004 — Thuyền thúng Bảy Mẫu Hội An

**Nội dung query:**
```
Tìm khách sạn ở Hội An có thể đặt trải nghiệm thuyền thúng rừng dừa Bảy Mẫu
```
- Hard filter: `city` = Hội An

**Mục đích test:** Activities basket boat rừng dừa

**Expected outcome — Top 5:**
1. Grand Sunrise Palace Hoi An
2. Sunora Villa Hoi An
3. Sunkissed Paddy Hoi An Villa
4. ViVi An Bang Hotel
5. Hoi An Dream City Hotel

---

### GS-ACT-005 — Alpine Coaster Datanla Đà Lạt

**Nội dung query:**
```
Tìm khách sạn ở Đà Lạt có thể đặt trải nghiệm máng trượt Alpine Coaster Datanla
```
- Hard filter: `city` = Đà Lạt

**Mục đích test:** Activities Alpine Coaster / xe trượt Datanla

**Expected outcome — Top 5:**
1. Muong Thanh Dalat Hotel
2. Golden Sun Hotel - Dalat
3. Tala Dalat Hotel
4. Sunset Hill Hotel
5. A25 Hotel - 386 Hai Ba Trung Da Lat

---

### GS-ACT-006 — VinWonders/Safari Phú Quốc

**Nội dung query:**
```
Tìm khách sạn ở Đảo Phú Quốc có thể đặt vé VinWonders, Safari, Grand World
```
- Hard filter: `city` = Đảo Phú Quốc

**Mục đích test:** Activities VinWonders, Safari, Grand World, Hòn Thơm

**Expected outcome — Top 5:**
1. Wyndham Garden Grandworld Phu Quoc
2. Vinpearl Wonderworld Phu Quoc
3. Melia Vinpearl Phu Quoc
4. Robins Homestay Vinpearl Phu Quoc
5. ROVA HOTEL - POSITANO HORSE PHU QUOC

---

### GS-ACT-007 — Múa rối nước Thăng Long Hà Nội

**Nội dung query:**
```
Tìm khách sạn ở Hà Nội có thể đặt vé xem múa rối nước Thăng Long
```
- Hard filter: `city` = Hà Nội

**Mục đích test:** Activities show múa rối nước

**Expected outcome — Top 5:**
1. Minasi Premium Hotel
2. Tien Minh Hotel 113 Le Thanh Nghi
3. Studio cạnh Sheraton/Ban Công/Bồn Tắm/Bếp/Tây Hồ
4. Sofitel Legend Metropole Hanoi Hotel
5. L7 WEST LAKE HANOI by LOTTE HOTELS

---

### GS-ACT-008 — Tour Đại Nội, ca Huế Huế

**Nội dung query:**
```
Tìm khách sạn ở Huế có thể đặt tour tham quan Đại Nội, nghe ca Huế trên sông Hương
```
- Hard filter: `city` = Huế

**Mục đích test:** Activities tour Đại Nội / ca Huế sông Hương

**Expected outcome — Top 4** (corpus chỉ có 4 KS Huế thoả, < top_k=5):
1. TTC Imperial Hotel
2. Kobi Onsen Resort Hue
3. Huong Giang Hotel Resort & Spa
4. Melia Vinpearl Hue

---

### GS-ACT-009 — Suối khoáng Núi Thần Tài Đà Nẵng

**Nội dung query:**
```
Tìm khách sạn ở Đà Nẵng có thể đặt vé Công viên suối khoáng nóng Núi Thần Tài
```
- Hard filter: `city` = Đà Nẵng

**Mục đích test:** Activities suối khoáng Núi Thần Tài

**Expected outcome — Top 5:**
1. Liberty Hotel Da Nang
2. DS HOTEL ĐÀ NẴNG
3. Muong Thanh Luxury Da Nang hotel
4. Wyndham Soleil Danang
5. Muong Thanh Luxury Song Han Hotel

---

### GS-ACT-010 — Tour Ninh Bình trong ngày từ Hà Nội

**Nội dung query:**
```
Tìm khách sạn ở Hà Nội có thể đặt tour Ninh Bình (Tràng An, Bái Đính, Tam Cốc) trong ngày
```
- Hard filter: `city` = Hà Nội

**Mục đích test:** Activities day tour Ninh Bình khởi hành từ Hà Nội

**Expected outcome — Top 5:**
1. A25 Premium Hotel - 130 Bà Triệu
2. Hanoian Hotel
3. Hanoi Lucky Hotel
4. Hanoi Gallant Hotel
5. Muong Thanh Grand Hanoi Hotel

---

## GS-POL — Policies (1–10)

**Mục đích nhóm:** Kiểm tra retrieval từ **policyNotes** (`secondary.hotel_policy`) — chính sách trẻ em, giường phụ, giấy tờ, độ tuổi nhận phòng.

Ground truth xếp theo `review_score` giảm dần.

---

### GS-POL-001 — Trẻ em miễn phí Hà Nội

**Nội dung query:**
```
Tìm khách sạn ở Hà Nội cho trẻ em ở miễn phí khi dùng giường có sẵn
```
- Hard filter: `city` = Hà Nội, `suitable_for` = Gia đình có trẻ nhỏ

**Mục đích test:** Policy "ở miễn phí nếu sử dụng giường có sẵn"

**Expected outcome — Top 5:**
1. Hanoi Sail Hotel
2. Studio cạnh Sheraton/Ban Công/Bồn Tắm/Bếp/Tây Hồ
3. Minasi Grand Hotel
4. JW Marriott Hotel Hanoi
5. A25 Premium Hotel - 130 Bà Triệu

---

### GS-POL-002 — Trẻ em miễn phí Hồ Chí Minh

**Nội dung query:**
```
Tìm khách sạn ở Hồ Chí Minh cho trẻ em ở miễn phí khi dùng giường có sẵn
```
- Hard filter: `city` = Hồ Chí Minh, `suitable_for` = Gia đình có trẻ nhỏ

**Mục đích test:** Policy trẻ em miễn phí trong policyNotes

**Expected outcome — Top 5:**
1. Express by M Village Điện Biên Phủ (The Tropic)
2. Vinpearl Landmark 81
3. Hilton Saigon
4. JW Marriott Hotel & Suites Saigon
5. A25 Premium Hotel - 142 Bùi Thị Xuân

---

### GS-POL-003 — Trẻ em miễn phí Đà Nẵng

**Nội dung query:**
```
Tìm khách sạn ở Đà Nẵng cho trẻ em ở miễn phí khi dùng giường có sẵn
```
- Hard filter: `city` = Đà Nẵng, `suitable_for` = Gia đình có trẻ nhỏ

**Mục đích test:** Policy trẻ em (ví dụ dưới 12 tuổi miễn phí)

**Expected outcome — Top 5:**
1. Marriott Executive Apartments Danang, Han River
2. Banyan Tree Lang Co
3. Luxury Apartment in Sheraton Building- Beach Front
4. Courtyard by Marriott Danang Han River
5. Pullman Danang Beach Resort

---

### GS-POL-004 — Giường phụ Hà Nội

**Nội dung query:**
```
Tìm khách sạn ở Hà Nội có chính sách giường phụ (extra bed)
```
- Hard filter: `city` = Hà Nội

**Mục đích test:** Policy extra bed trong policyNotes

**Expected outcome — Top 5:**
1. Hanoi Sail Hotel
2. Studio cạnh Sheraton/Ban Công/Bồn Tắm/Bếp/Tây Hồ
3. Sofitel Legend Metropole Hanoi Hotel
4. Minasi Grand Hotel
5. L7 WEST LAKE HANOI by LOTTE HOTELS

---

### GS-POL-005 — Giường phụ Hồ Chí Minh

**Nội dung query:**
```
Tìm khách sạn ở Hồ Chí Minh có chính sách giường phụ (extra bed)
```
- Hard filter: `city` = Hồ Chí Minh

**Mục đích test:** Policy extra bed

**Expected outcome — Top 5:**
1. TalaSaiGon Hotel
2. Express by M Village Điện Biên Phủ (The Tropic)
3. Vinpearl Landmark 81
4. Hilton Saigon
5. Sheraton Saigon Grand Opera Hotel

---

### GS-POL-006 — Giường phụ Đà Nẵng

**Nội dung query:**
```
Tìm khách sạn ở Đà Nẵng có chính sách giường phụ (extra bed)
```
- Hard filter: `city` = Đà Nẵng

**Mục đích test:** Policy extra bed

**Expected outcome — Top 5:**
1. Marriott Executive Apartments Danang, Han River
2. Hampton Danang Luxury Apartment
3. Banyan Tree Lang Co
4. Luxury Apartment in Sheraton Building- Beach Front
5. Courtyard by Marriott Danang Han River

---

### GS-POL-007 — Giấy tờ tùy thân Vũng Tàu

**Nội dung query:**
```
Tìm khách sạn ở Vũng Tàu yêu cầu xuất trình giấy tờ tùy thân khi nhận phòng
```
- Hard filter: `city` = Vũng Tàu

**Mục đích test:** Policy yêu cầu CMND/hộ chiếu khi check-in

**Expected outcome — Top 5:**
1. Holiday Inn Resort Ho Tram Beach By IHG
2. Melia Ho Tram Beach Resort
3. ibis Styles Vung Tau
4. Dhawa Ho Tram
5. IXORA Ho Tram by Fusion

---

### GS-POL-008 — Giấy tờ tùy thân Nha Trang

**Nội dung query:**
```
Tìm khách sạn ở Nha Trang yêu cầu xuất trình giấy tờ tùy thân khi nhận phòng
```
- Hard filter: `city` = Nha Trang

**Mục đích test:** Policy ID required — ưu tiên KS nêu rõ yêu cầu giấy tờ

**Expected outcome — Top 5:**
1. TTC Hotel - Michelia
2. Anrizon Hotel Nha Trang
3. Vinpearl Resort Nha Trang
4. Vinpearl Luxury Nha Trang
5. Vinpearl Beachfront Nha Trang

---

### GS-POL-009 — Giấy tờ tùy thân Phú Quốc

**Nội dung query:**
```
Tìm khách sạn ở Đảo Phú Quốc yêu cầu xuất trình giấy tờ tùy thân khi nhận phòng
```
- Hard filter: `city` = Đảo Phú Quốc

**Mục đích test:** Policy ID / giấy khai sinh khi check-in

**Expected outcome — Top 5:**
1. Sheraton Phu Quoc Long Beach Resort
2. Melia Vinpearl Phu Quoc
3. Vinholidays Fiesta Phú Quốc
4. Vinpearl Resort & Spa Phú Quốc
5. Vinpearl Wonderworld Phu Quoc

---

### GS-POL-010 — Độ tuổi nhận phòng ≥18 Hồ Chí Minh

**Nội dung query:**
```
Tìm khách sạn ở Hồ Chí Minh yêu cầu khách nhận phòng phải từ 18 tuổi trở lên
```
- Hard filter: `city` = Hồ Chí Minh

**Mục đích test:** Policy min age 18 trong policyNotes

**Expected outcome — Top 5:**
1. Express by M Village Điện Biên Phủ (The Tropic)
2. Liberty Central Saigon Citypoint Hotel
3. Express by M Village Điện Biên Phủ Q3
4. Liberty Central Saigon Riverside Hotel
5. Liberty Central Saigon Centre Hotel

---

## GS-AMEN — Amenities (1–10)

**Mục đích nhóm:** Kiểm tra retrieval + hard filter theo **tag amenities** chuẩn hóa.

Ground truth xếp theo `review_score` giảm dần trong số KS có đủ amenity tag.

---

### GS-AMEN-001 — Bể bơi ngoài trời Nha Trang

**Nội dung query:**
```
Tìm khách sạn ở Nha Trang có bể bơi ngoài trời
```
- Hard filter: `city` = Nha Trang, `amenities` = ["Bể bơi ngoài trời"]

**Mục đích test:** Tag amenity `Bể bơi ngoài trời`

**Expected outcome — Top 5:**
1. Vinpearl Luxury Nha Trang
2. TTC Van Phong Bay Resort
3. Sheraton Nha Trang Hotel & Spa
4. The Westin Resort & Spa Cam Ranh
5. JW Marriott Cam Ranh Bay Resort & Spa

---

### GS-AMEN-002 — Quán bar cạnh bể bơi Phú Quốc

**Nội dung query:**
```
Tìm resort ở Đảo Phú Quốc có quán bar cạnh bể bơi
```
- Hard filter: `city` = Đảo Phú Quốc, `amenities` = ["Quán bar cạnh bể bơi"]

**Mục đích test:** Tag `Quán bar cạnh bể bơi`

**Expected outcome — Top 5:**
1. Lahana Resort Phu Quoc & Spa
2. Thien Thanh Phu Quoc Resort
3. La Festa Phu Quoc, Curio Collection by Hilton
4. Vinholidays Fiesta Phú Quốc
5. Roma Hotel Phu Quoc

---

### GS-AMEN-003 — Bể bơi trẻ em Vũng Tàu

**Nội dung query:**
```
Tìm khách sạn ở Vũng Tàu có bể bơi trẻ em
```
- Hard filter: `city` = Vũng Tàu, `amenities` = ["Bể bơi trẻ em"]

**Mục đích test:** Tag `Bể bơi trẻ em`

**Expected outcome — Top 5:**
1. Holiday Inn Resort Ho Tram Beach By IHG
2. Melia Ho Tram Beach Resort
3. ibis Styles Vung Tau
4. Hai Long Hotel
5. Dhawa Ho Tram

---

### GS-AMEN-004 — Phòng tập Hà Nội

**Nội dung query:**
```
Tìm khách sạn ở Hà Nội có phòng tập gym
```
- Hard filter: `city` = Hà Nội, `amenities` = ["Phòng tập"]

**Mục đích test:** Tag `Phòng tập`

**Expected outcome — Top 5:**
1. Hanoi Sail Hotel
2. Sofitel Legend Metropole Hanoi Hotel
3. Minasi Grand Hotel
4. L7 WEST LAKE HANOI by LOTTE HOTELS
5. JW Marriott Hotel Hanoi

---

### GS-AMEN-005 — Spa/mát-xa Đà Nẵng

**Nội dung query:**
```
Tìm khách sạn ở Đà Nẵng có dịch vụ spa, mát-xa
```
- Hard filter: `city` = Đà Nẵng, `amenities` = ["Mát-xa"]

**Mục đích test:** Tag `Mát-xa` / Spa

**Expected outcome — Top 5:**
1. Banyan Tree Lang Co
2. Pullman Danang Beach Resort
3. Danang Marriott Resort & Spa, Non Nuoc Beach Villas
4. Danang Marriott Resort & Spa
5. Melia Vinpearl Danang Riverfront

---

### GS-AMEN-006 — Khu vườn Hội An

**Nội dung query:**
```
Tìm khách sạn ở Hội An có khu vườn
```
- Hard filter: `city` = Hội An, `amenities` = ["Vườn"]

**Mục đích test:** Tag `Vườn`

**Expected outcome — Top 5:**
1. Grand Sunrise Palace Hoi An
2. Four Seasons Resort The Nam Hai Hoi An Vietnam
3. Sunora Villa Hoi An
4. The Nam An Villa Hoi An
5. Gia Huy Riverside Hotel Hoi An

---

### GS-AMEN-007 — Bãi biển riêng Phú Quốc

**Nội dung query:**
```
Tìm resort ở Đảo Phú Quốc có bãi biển riêng
```
- Hard filter: `city` = Đảo Phú Quốc, `amenities` = ["Bãi biển riêng"]

**Mục đích test:** Tag `Bãi biển riêng`

**Expected outcome — Top 5:**
1. JW Marriott Phu Quoc Emerald Bay Resort & Spa
2. Thien Thanh Phu Quoc Resort
3. Roma Hotel Phu Quoc
4. Vida Loca Phu Quoc Resort
5. Sheraton Phu Quoc Long Beach Resort

---

### GS-AMEN-008 — Nhà hàng Hồ Chí Minh

**Nội dung query:**
```
Tìm khách sạn ở Hồ Chí Minh có nhà hàng trong khuôn viên
```
- Hard filter: `city` = Hồ Chí Minh, `amenities` = ["Nhà hàng"]

**Mục đích test:** Tag `Nhà hàng`

**Expected outcome — Top 5:**
1. Vinpearl Landmark 81
2. Hilton Saigon
3. Sheraton Saigon Grand Opera Hotel
4. JW Marriott Hotel & Suites Saigon
5. A25 Premium Hotel - 142 Bùi Thị Xuân

---

### GS-AMEN-009 — Không hút thuốc Hồ Chí Minh

**Nội dung query:**
```
Tìm khách sạn ở Hồ Chí Minh hoàn toàn không hút thuốc
```
- Hard filter: `city` = Hồ Chí Minh, `amenities` = ["Hoàn toàn không hút thuốc"]

**Mục đích test:** Tag `Hoàn toàn không hút thuốc`

**Expected outcome — Top 5:**
1. TalaSaiGon Hotel
2. Express by M Village Điện Biên Phủ (The Tropic)
3. Vinpearl Landmark 81
4. Hilton Saigon
5. Sheraton Saigon Grand Opera Hotel

---

### GS-AMEN-010 — Sân chơi trẻ em Nha Trang

**Nội dung query:**
```
Tìm khách sạn ở Nha Trang có sân chơi cho trẻ em
```
- Hard filter: `city` = Nha Trang, `amenities` = ["Sân chơi"]

**Mục đích test:** Tag `Sân chơi`

**Expected outcome — Top 5:**
1. Sheraton Nha Trang Hotel & Spa
2. The Westin Resort & Spa Cam Ranh
3. JW Marriott Cam Ranh Bay Resort & Spa
4. Novotel Nha Trang Hotel
5. Meliá Vinpearl Cam Ranh Beach Resort

---

## Tóm tắt đánh giá

### Metric gợi ý

| Metric | Mô tả |
|--------|--------|
| Recall@5 | % query có ≥1 ground-truth KS trong top 5 |
| MRR@5 | Mean Reciprocal Rank của KS relevant đầu tiên |
| nDCG@5 | Thứ tự ranking so với ground truth |
| Filter accuracy | Hard filter (city, amenities...) áp dụng đúng |

### Điểm đặc biệt cần lưu ý

1. **GS-DESC:** Câu trả lời chỉ có trong description — test semantic retrieval, không dựa tag.
2. **GS-FAQ vs GS-AMEN:** Cùng hỏi "bể bơi" nhưng FAQ (GS-FAQ-005) lấy từ faq, AMEN lấy từ tag amenities — pipeline phải retrieve đúng nguồn.
3. **GS-ACT-008:** Chỉ 4 KS Huế thoả — đánh giá với top 4, không expect 5.
4. **Ground truth:** Tên KS chưa map ID — cần normalize tên khi so sánh với API response.
5. Tất cả query: `intent_type` = `hotel_search` — không test destination_info/comparison.

---

*Tài liệu sinh từ `golden_set_v1.json` — Labeler: Kiên, version v1*
