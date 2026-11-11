# Kiến trúc hệ thống La Bàn Kỹ Năng

Tài liệu củng cố các thông tin kỹ thuật hiện hành của hệ thống La Bàn Kỹ Năng dành cho đội ngũ phát triển và bảo trì.

## 1. Bản đồ học kỳ và tập môn lựa chọn (Selection & Curriculum Mappings)

- **Mapping nguồn học kỳ**: File căn cứ `semestermap.json` tại thư mục gốc định nghĩa danh mục môn học, phân bổ học kỳ (kỳ 1 đến kỳ 9) và hai nhánh chuyên ngành (COMBO): **Applied Data Science** và **AI application**.
- **Quy tắc chọn môn**:
  - Kỳ 1–4 dùng chung cho cả hai nhánh.
  - Kỳ 5–9 phụ thuộc COMBO đã chọn; mỗi nhánh có 37 môn (tổng hợp 2 nhánh là 41 mã học phần duy nhất).
  - Chọn môn kỳ $N$ tự động chọn toàn bộ môn kỳ trước; bỏ môn kỳ $N$ sẽ bỏ toàn bộ các môn kỳ sau.
  - Môn ngoài danh mục dữ liệu đối chiếu nội bộ vẫn được lưu trong selection bình thường; chỉ các môn có dữ liệu nội bộ mới tham gia cung cấp bằng chứng (evidence).
- **Endpoint**: API `/api/v1/selections` tiếp nhận tập môn và kiểm tra tính hợp lệ về COMBO và membership trong `semestermap.json`.

## 2. Đối chiếu mục tiêu CWA, JD và cơ chế trục radar (Target Axes)

- **Mục tiêu CWA (Hồ sơ nghề nghiệp được cung cấp)**:
  - Dựa trên 6 hồ sơ CWA được cung cấp trong `data/AI_Roles_CWA_18398_2026` ([ADR 0001](adr/0001-use-provided-cwa-career-groups.md)). Đây là các bản tóm tắt hồ sơ do dự án cung cấp, không phải toàn bộ tiêu chuẩn hay chứng chỉ CWA chính thức.
  - Danh mục hệ thống cung cấp 8 vị trí lựa chọn, phân tách ML, CV và NLP/LLM thành các phạm vi mục tiêu riêng.
  - **Trục cố định (Fixed axes)**: Mỗi vị trí có đúng 5 trục cố định (tên tiếng Anh, thứ tự, mô tả phạm vi tiếng Việt) được snapshot cố định vào phiên ([ADR 0004](adr/0004-fixed-cwa-target-axes.md)). Điểm tổng (overall score, thang 0–5) do mô hình trực tiếp đánh giá trong phạm vi 5 trục, không vượt quá điểm trục cao nhất.
- **Mục tiêu JD (Job Description)**:
  - Người dùng cung cấp trực tiếp văn bản mô tả công việc (hỗ trợ định dạng plain text hoặc Markdown).
  - **Trục động (Dynamic axes)**: 5 trục đánh giá do LLM tự xác định dựa trên toàn bộ yêu cầu của JD ([ADR 0003](adr/0003-model-defined-career-radar.md)).
  - Đánh giá từng yêu cầu với 3 mức độ bao phủ: `covered`, `related`, `not_evidenced`.

## 3. Ranh giới dữ liệu máy chủ và hợp đồng công khai (Server-Source vs Public DTO Boundary)

- **Dữ liệu nguồn nội bộ (Server-only)**:
  - Tọa lạc tại `data/courses/<code>/clos.json`. Đây là dữ liệu enriched authoritative chỉ nằm ở phía backend máy chủ.
  - *Lưu ý về mã nguồn mở*: Trong ứng dụng triển khai, dữ liệu này chỉ nằm ở server; tuy nhiên nếu repository được công khai, bất kỳ dữ liệu nào commit trong Git đều hiển thị.
- **Bảo vệ nội dung nội bộ**:
  - API công khai không trả về mô tả CLO nội bộ, snapshot học phần hoặc fingerprint nội bộ.
  - DTO công khai (`career_comparison`, `course_jd_comparison`) chỉ chứa `course_code` làm evidence.
  - Backend guard chặn các phản hồi chứa trích dẫn nguyên văn dài hoặc chuỗi 12 từ liên tiếp từ nguồn nội bộ trước khi commit vào DB; lớp public projection lọc kết quả và lịch sử Chat trước khi trả về client.

## 4. Hàng đợi tác vụ bền vững, Worker và Idempotency (Durable Queue, Worker, Replay)

- **Phân tách tiến trình & Cơ sở dữ liệu**:
  - API server (FastAPI) và background worker (`app.jobs.worker_cli`) chạy trên hai tiến trình riêng biệt, chia sẻ chung cơ sở dữ liệu SQLite mặc định tại `var/skillbridge-clo-jd.sqlite3` (có thể tùy biến qua biến môi trường `SKILLBRIDGE_DATABASE_PATH`).
- **Hàng đợi bền vững**:
  - Bảng tác vụ lưu trạng thái bền vững trong DB gồm: `queued`, `processing`, `succeeded`, `failed`, `interrupted`.
  - Khi chiếu ra DTO công khai phục vụ API/frontend, trạng thái bền vững `succeeded` được ánh xạ thành `ready` (`job_repository.py`).
  - Hệ thống sử dụng cơ chế leasing/fencing để đảm bảo an toàn đơn tuyến khi worker nhận job.
  - Session snapshot lưu toàn bộ trạng thái tại thời điểm khởi tạo kèm fingerprint SHA-256 ([ADR 0002](adr/0002-pin-career-target-in-session.md)).
- **Vòng đời Frontend, Idempotency & Replay**:
  - Thao tác reload trang trên frontend chỉ thực hiện truy vấn GET trạng thái (`/advisor/sessions/{id}` hoặc recommendations); không tự động gửi lại POST hay tự ý xếp hàng/kích hoạt inference mới.
  - Replay thủ công khi cần phục hồi (ví dụ sau khi mất kết nối) sử dụng capability token và idempotency key ổn định đã lưu trong workspace tab.
- **Không tự động retry suy luận (No automatic inference retry)**:
  - Nếu tác vụ thất bại, worker lưu mã lỗi an toàn (ví dụ: `model_output_limit`, `invalid_structured_output`, `invalid_evidence`, `private_policy_disclosure`).
  - Hệ thống không tự động retry để tránh phát sinh chi phí hoặc lặp lại lỗi không an toàn.
  - Operator có thể can thiệp thủ công thông qua CLI với cờ xác nhận có kiểm soát:

    ```bash
    .venv/bin/python -m app.jobs.worker_cli --retry-job <job_id> --acknowledge-possible-duplicate
    .venv/bin/python -m app.jobs.worker_cli --once
    ```

## 5. Cache kết quả tùy chọn (Result Cache)

- Bật qua biến môi trường `SKILLBRIDGE_RESULT_CACHE_DIR` (mặc định tắt).
- Khi bật, kết quả so sánh CWA/JD và bộ gợi ý Coursera đã được xác thực sẽ được lưu vào file atomic (quyền `0600`) trong thư mục chỉ định.
- Khóa cache được băm từ nội dung môn học, mục tiêu, model parameters và mã policy. Cache hit trả ngay kết quả mà không khởi tạo OpenAI client SDK hay tốn chi phí gọi API.

## 6. Gợi ý khóa học Coursera (Coursera Suggestions)

- Theo [ADR 0005](adr/0005-durable-coursera-suggestions.md), gợi ý khóa học được kích hoạt theo nút bấm chủ động của người dùng sau khi đã có kết quả đối chiếu sẵn sàng.
- Tái sử dụng cùng hàng đợi và worker của hệ thống; mỗi phiên chỉ lưu tối đa 5 khóa học gắn liền với các khoảng trống (gaps) được ghi nhận.
- Khóa học yêu cầu có title và URL citations hợp lệ từ API Responses web search; Chat trong phiên chỉ giải thích trên danh sách khóa học đã lưu, không thực hiện tìm kiếm web bổ sung.

## 7. Phụ thuộc dữ liệu thời gian chạy (Runtime Data Dependencies)

Các đường dẫn dữ liệu mặc định được sử dụng tại runtime (`app/services/course_service.py:49-52`):

- `semestermap.json`: Danh mục và cấu trúc kỳ học, xác thực tập môn và COMBO.
- `data/AI_Roles_CWA_18398_2026/`: 6 hồ sơ CWA nguồn được cung cấp.
- `data/courses/`: Dữ liệu enriched CLO nội bộ theo từng mã học phần (`data/courses/<code>/clos.json`).
- `data/stage1/subjects`: Thư mục dữ liệu môn học giai đoạn 1.
- `data/stage1/combo_slot_map.json`: Bản đồ mapping slot môn học cho các nhánh COMBO.
- `data/flm_output/subjects`: Thư mục dữ liệu môn học từ FLM.
