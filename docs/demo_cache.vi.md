# Hướng dẫn thiết lập cache kết quả demo — CWA Data Analyst và JD AI Engineer Intern

Tài liệu hướng dẫn cấu hình và thiết lập cache kết quả phía server cho kịch bản demo đối chiếu môn học (COMBO Applied Data Science, học kỳ 5) với hai mục tiêu:

- Nhóm nghề CWA: **Data Analyst** (dựa trên hồ sơ CWA được cung cấp).
- JD tuyển dụng: vị trí **AI Engineer Intern** từ [ai_engineer_intern_jd.md](../examples/ai_engineer_intern_jd.md).

Khi được kích hoạt, cache lưu trữ toàn bộ nội dung đối chiếu đã xác thực (tổng quan, radar, nhận định, khoảng trống, môn dẫn chứng) cùng danh sách gợi ý Coursera tương ứng. Không lưu token bảo mật, ID phiên hay lịch sử Chat trong cache.

## Cấu hình kích hoạt cache tùy chọn

Cache mặc định tắt trong mã nguồn và `.env.example`. Để bật tính năng này trên máy phát triển, thêm biến sau vào `.env.local`:

```dotenv
SKILLBRIDGE_RESULT_CACHE_DIR=var/demo-result-cache
```

Khởi động cả API và worker bằng cùng cấu hình `.env.local` như trong [hướng dẫn chạy live](live_guide.md).

## Cơ chế tạo và tái sử dụng cache

- **Khởi tạo dữ liệu cache**: Một bản clone mã nguồn sạch không đi kèm sẵn các tệp cache cục bộ (thư mục `var/` nằm trong `.gitignore`). Trong lượt chạy đầu tiên với mỗi mục tiêu, worker sẽ gọi API mô hình thực tế để sinh kết quả (có phát sinh chi phí), sau đó tự động lưu vào thư mục cache nếu hợp lệ. Kịch bản chuẩn bị 4 bản ghi cache cho tình huống 2 mục tiêu này (kết quả đối chiếu và gợi ý Coursera cho mỗi mục tiêu) là quy trình chuẩn bị trước buổi demo, không phải trạng thái có sẵn trong kho mã nguồn.
- **Tái sử dụng khi demo**:
  1. Chọn COMBO **Applied Data Science** và **Học kỳ 5**.
  2. Chọn **Data Analyst** → **Khám phá nhóm nghề**. Worker tìm thấy cache hit và trả ngay kết quả đã lưu mà không gọi API OpenAI.
  3. Bấm **Gợi ý khóa học** để đọc bộ gợi ý Coursera đã cache.
  4. Bấm **So sánh mục tiêu khác**, dán nội dung JD từ file mẫu → **So sánh với JD**.
  5. Bấm **Gợi ý khóa học** trên kết quả JD để tái sử dụng gợi ý đã lưu.

Các bước vẫn tạo phiên và tác vụ riêng biệt để đảm bảo an toàn phiên; UI có thể hiển thị trạng thái chờ ngắn theo chu kỳ polling. Chat luôn gọi mô hình trực tiếp theo ngữ cảnh phiên và không lưu vào cache. Nút **Tải lại trạng thái gợi ý** chỉ thực hiện thao tác GET trạng thái hiện tại, không tự động tìm lại khóa học hay kích hoạt đối chiếu lại.

## Cơ chế bảo vệ và chuẩn hóa khóa cache

- **Chuẩn hóa khóa JD**: Khóa cache phụ thuộc nội dung nguồn môn học, mục tiêu, tham số mô hình và phiên bản policy. Khi băm khóa cho JD, hệ thống tự động chuẩn hóa bằng cách bỏ qua dòng trống, khoảng trắng thừa, dấu tiêu đề Markdown, in đậm và ký tự bullet đầu dòng, cho phép sao chép dạng Markdown hay text hiển thị mà vẫn khớp khóa. Nếu thay đổi nội dung ngữ nghĩa (ví dụ: đổi "and" thành "or", thay đổi yêu cầu), khóa sẽ thay đổi và tạo cache miss.
- **An toàn và cô lập**: Tệp cache được ghi atomically tại thư mục `var/` máy chủ với quyền `0600`. Tệp cache hỏng hoặc không vượt qua kiểm tra cấu trúc sẽ bị từ chối và không âm thầm sinh lại bằng AI. Cache hit không tạo SDK client và không chia sẻ lịch sử hay capability token giữa các phiên.

Cache không tự hết hạn; thông tin Coursera phản ánh thời điểm kết quả được lưu và cần được kiểm tra lại trên trang khóa học. Các cache miss đồng thời có thể cùng gọi AI; cache hiện không có cơ chế khóa để gộp các lượt sinh trùng nhau.
