# La Bàn Kỹ Năng

La Bàn Kỹ Năng là hệ thống hỗ trợ sinh viên đối chiếu nội dung các học phần đã chọn với yêu cầu của nhóm nghề nghiệp (theo 6 hồ sơ CWA được cung cấp) hoặc mô tả công việc cụ thể (JD do người dùng cung cấp), đồng thời hỗ trợ hỏi đáp giải thích chi tiết và gợi ý khóa học Coursera bổ trợ.

## Mục đích và giới hạn

- **Mục đích**: Phân tích mức độ liên quan, độ sâu kiến thức và các khoảng trống nội dung giữa tập môn học đã chọn với mục tiêu nghề nghiệp; trực quan hóa qua biểu đồ radar 5 trục và hỗ trợ Chat theo ngữ cảnh phiên.
- **Giới hạn**:
  - Việc chọn môn chỉ phản ánh phạm vi học phần người dùng lựa chọn dùng làm căn cứ đối chiếu; không xác nhận sinh viên đã hoàn thành môn học, kết quả điểm số, năng lực cá nhân, kinh nghiệm làm việc thực tế hay khả năng trúng tuyển.
  - Sáu hồ sơ CWA là các bản tóm tắt hồ sơ nhóm nghề do dự án cung cấp, không phải toàn bộ tiêu chuẩn hay chứng chỉ CWA chính thức.
  - Điểm tổng và điểm các trục trên radar (thang 0–5) là nhận định đối chiếu nội dung do mô hình trực tiếp đánh giá, không phải thang điểm chính thức của CWA hay chứng chỉ hành nghề.
  - Gợi ý khóa học Coursera dựa trên trích dẫn web từ mô hình; người học cần kiểm tra thông tin thực tế trên trang khóa học.
  - *Lưu ý về dữ liệu*: Trong ứng dụng triển khai, dữ liệu môn học nằm ở server. Tuy nhiên, trong một repository Git công khai, toàn bộ dữ liệu commit kèm mã nguồn sẽ được hiển thị công khai.

## Cài đặt từ đầu

Yêu cầu môi trường:

- Python >= 3.10
- Node.js >= 22.12 (khớp cấu hình `frontend/package.json`, khuyến nghị dùng Node 24 qua NVM)

### 1. Khởi tạo môi trường Python

Tại thư mục gốc dự án:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Cài đặt frontend

```bash
cd frontend
npm ci
cd ..
```

## Chạy demo offline trong 2 terminal

Chế độ demo offline chạy với catalog thật và 2 tiến trình API/worker giả lập, không gọi API OpenAI thật và không tốn chi phí.

- **Terminal 1 (Backend Demo Launcher)**:

  ```bash
  .venv/bin/python -m examples.offline_demo
  ```

  *(Tiến trình chạy API tại `http://127.0.0.1:8001` và mock worker)*

- **Terminal 2 (Frontend Dev Server)**:

  ```bash
  cd frontend
  VITE_API_BASE_URL=http://127.0.0.1:8001 VITE_DEMO=true npm run dev
  ```

Mở trình duyệt tại **http://localhost:5173**. Nhấn `Ctrl+C` tại Terminal 1 khi muốn dừng (script tự dọn dẹp các tiến trình con và DB tạm).

Để chạy với môi trường live gọi OpenAI thật (cần 3 terminal: API, worker, frontend và cấu hình API key), xem chi tiết tại [Hướng dẫn chạy live](docs/live_guide.md).

## Kiểm thử, build và E2E

### Backend

```bash
# Chạy bộ kiểm thử pytest
.venv/bin/python -m pytest
```

### Frontend

Tại thư mục `frontend/`:

```bash
# Chạy unit tests (Vitest)
npm test

# Kiểm tra TypeScript và build production
npm run build

# Cài đặt trình duyệt Playwright Chromium (cho E2E tests)
npm exec playwright install chromium

# Chạy E2E tests (tự động khởi chạy mock API và Vite server)
npm run test:e2e
```

## Vị trí dữ liệu nguồn bắt buộc

Hệ thống yêu cầu các dữ liệu nguồn tại thời gian chạy (theo cấu hình mặc định trong `app/services/course_service.py` và `semestermap.json`):

- `semestermap.json`: Cấu trúc phân bổ môn học theo 9 học kỳ và 2 nhánh chuyên ngành (COMBO).
- `data/AI_Roles_CWA_18398_2026/`: 6 hồ sơ CWA nguồn được cung cấp.
- `data/courses/<code>/clos.json`: Dữ liệu enriched CLO nội bộ theo từng mã học phần dùng cho phân tích đối chiếu.
- `data/stage1/subjects`: Thư mục dữ liệu môn học giai đoạn 1.
- `data/stage1/combo_slot_map.json`: Bản đồ mapping slot môn học cho các nhánh COMBO.
- `data/flm_output/subjects`: Thư mục dữ liệu môn học từ FLM.

## Cấu trúc thư mục chính

```
.
├── app/                  # FastAPI backend, engines đối chiếu, services, hàng đợi và API endpoints
├── frontend/             # Ứng dụng giao diện React, TypeScript, Vite
│   ├── src/              # Components, styles và kiểm thử
│   └── package.json
├── data/                 # Hồ sơ CWA được cung cấp và dữ liệu học phần
├── docs/                 # Tài liệu kiến trúc, hướng dẫn và quyết định thiết kế (ADRs)
├── examples/             # Các kịch bản demo và payload mẫu
├── tests/                # Bộ kiểm thử pytest cho backend
├── semestermap.json      # Bản đồ môn học và kỳ học
├── requirements.txt      # Thư viện runtime bắt buộc cho backend
├── requirements-crawl.txt # Thư viện tùy chọn cho crawler
└── README.md
```

## Công cụ thu thập dữ liệu tùy chọn

Dự án có sẵn các script crawler tùy chọn (`flm_crawler.py`, `flm_crawler_combo.py`) để thu thập dữ liệu giáo trình. Các script này không thuộc runtime chính của ứng dụng.

Nếu cần sử dụng:

```bash
pip install -r requirements-crawl.txt
python -m playwright install chromium
```

*(Lưu ý: Không tự ý chạy crawler khi không có nhu cầu cập nhật dữ liệu).*

## Mục lục tài liệu

- [Tài liệu kiến trúc tổng quan](docs/architecture.md): Phân tích chi tiết kiến trúc, biên giới dữ liệu, hàng đợi bền vững và radar 5 trục.
- [Hướng dẫn vận hành live](docs/live_guide.md): Cấu hình 3 tiến trình thực tế, quản lý worker và xử lý lỗi vận hành.
- [Cache kết quả demo](docs/demo_cache.vi.md): Thiết lập cache server-side cho demo offline/live.
- [Kịch bản demo](docs/demo_script.vi.md): Kịch bản chi tiết trình diễn các tính năng của sản phẩm.
- [Thuật ngữ và ngôn ngữ nghiệp vụ](GLOSSARY.md): Định nghĩa các khái niệm và thuật ngữ chuẩn hóa.
- [Mục lục tài liệu và các ADR](docs/README.md): Danh mục các bản ghi quyết định kiến trúc và quy ước agent.
