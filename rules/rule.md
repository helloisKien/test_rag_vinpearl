# Quy tắc làm việc
## 0. BẠN GỌI MÌNH LÀ MASTER NHÉ
## 1. Không tự chạy command

Bạn chỉ được:

* Phân tích
* Thiết kế
* Tạo file mới
* Chỉnh sửa nội dung file
* Đề xuất command cần chạy
* Hỏi mình để xin thêm thông tin

TẤT CẢ những CÔNG VIỆC KHÁC như:
Chạy command, Build, Test, Deploy, Git, Docker, Cài thư viện, phần mềm, Cấu hình tài khoản,Truy cập website, Chụp màn hình, vân vân....

bạn không được làm, khi nào làm đến các CÔNG VIỆC KHÁC trên, bạn hãy:

1. Dừng công việc hiện tại.
2. Hướng dẫn mình làm các bước để mình có thể làm và đưa kết quả cho bạn
3. Giải thích ngắn gọn mục đích.
4. Chờ mình gửi kết quả thực tế.
5. Chỉ tiếp tục sau khi đã nhận được kết quả.

Không được tự suy đoán kết quả command.

---

## 2. Duy trì Build Journal

Hãy duy trì file:

`.claude/build_state.md`

Đây là nguồn sự thật duy nhất (Single Source of Truth) về trạng thái hiện tại của dự án.

Nếu file chưa tồn tại thì hãy tạo nó ngay từ bước đầu tiên.

---

## 3. Nội dung bắt buộc của build_state.md

File phải luôn có cấu trúc sau:

# Project State

## Goal

Mục tiêu tổng thể của project.

## Current Plan

Tóm tắt phase hiện tại và mục tiêu của phase.

## Phase Progress

* [ ] Phase 0 - Environment & Infra
* [ ] Phase 1 - Ingest → PostgreSQL
* [ ] Phase 2 - Chunking
* [ ] Phase 3 - Embedding + Indexing
* [ ] Phase 4 - Retrieval Core
* [ ] Phase 5 - Intent Parsing
* [ ] Phase 6 - SearchAPI
* [ ] Phase 7 - ContextAPI
* [ ] Phase 8 - Observability
* [ ] Phase 9 - Evaluation
* [ ] Phase 10 - Final Reports

## Completed

Các công việc đã hoàn thành.

## Architecture Decisions

Các quyết định kiến trúc đã chốt và lý do lựa chọn.

## Issues

Các lỗi hoặc vấn đề phát sinh.

## Next Step

Bước tiếp theo cần thực hiện.

* [ ] Step 0 - .....
* [ ] Step 1 - .....
Step nào xong thì đánh dấu vào


## 4. Khi nào phải cập nhật build_state.md

Bắt buộc cập nhật build_state.md trong các trường hợp sau:

### A. Hoàn thành một Phase

Ví dụ:



Phải cập nhật:

* Phase Progress
* Completed theo format:
   [ ] Phase 0 hoàn thành ...
* Next Step



### B. Khi chốt một quyết định kiến trúc mới

Ví dụ:

* chọn SQLAlchemy thay vì asyncpg
* chọn cấu trúc thư mục mới
* thay đổi contract nội bộ

Phải ghi vào mục Architecture Decisions cùng lý do.



### C. KHI bạn gặp những CÔNG VIỆC KHÁC cần mình tự làm để gửi kết quả cho bạn

Cập nhật Completed theo format:
- Đã tạo file..../chỉnh sửa file..../tạo code ở file.... nhằm mục đích (1 câu tóm tắt mục đích ngắn thôi)
- Yêu cầu người dùng ..... nhằm mục đích .....
và Next Step theo format: [ ] Step n - Sau khi nhận kết quả của người dùng cần tạo file..../chỉnh sửa file..../tạo code ở file.... nhằm mục đích ...

---

## 5. Tiếp tục ở chat mới

Khi bắt đầu một phiên làm việc mới:

1. Luôn đọc `.claude/build_state.md` trước.
2. Coi đó là trạng thái chính thức của dự án.
3. Tóm tắt:

   * Phase hiện tại
   * Các việc đã hoàn thành
   * Các việc còn lại
4. Xác định Next Step.
5. Sau đó mới tiếp tục công việc.

---

## 6. Cách làm việc

* Luôn bám sát `@docs/VuDucKien_build_plan.md`.
* Mỗi lần chỉ xử lý một nhiệm vụ rõ ràng.
* Ưu tiên hoàn thành Acceptance Criteria của Phase hiện tại trước khi chuyển sang Phase tiếp theo.
* Không bỏ qua Acceptance Criteria.
* Nếu thiếu thông tin hoặc cần kết quả command thì phải dừng và yêu cầu mình cung cấp.

Trước khi chuyển sang bước tiếp theo, hãy tự kiểm tra xem build_state.md đã được cập nhật đầy đủ chưa.