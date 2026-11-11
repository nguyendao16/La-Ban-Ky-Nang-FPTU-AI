# La Bàn Kỹ Năng frontend

React/TypeScript/Vite, giao diện cam–trắng với xanh lam/xanh lá làm màu phụ. Luồng chính: **Môn học + Nhóm nghề CWA → Đối chiếu → Kết quả & Chat**. Tab JD hỗ trợ mục tiêu tuyển dụng riêng. Không có màn xác nhận dữ liệu nội bộ.

## Chạy và kiểm tra

Node >=22.12; môi trường verification dùng Node24 qua NVM.

```bash
cd frontend
npm ci
npm test
npm run build
npm exec playwright install chromium
npm run test:e2e
```

Demo: tại root chạy `.venv/bin/python -m examples.offline_demo`; terminal frontend chạy `VITE_API_BASE_URL=http://127.0.0.1:8001 VITE_DEMO=true npm run dev`. Mở `http://localhost:5173`. E2E tự quản lý hai processes API/fake worker và Vite, kiểm tra desktop/mobile, không cần key. Các ports8001/5173 phải trống. Khi cổng frontend đang dùng cho live, chạy `SKILLBRIDGE_E2E_WEB_PORT=5174 npm run test:e2e`; fake API và CORS demo tự dùng origin tương ứng.

Runtime thật: xem [README root](../README.md). API tại `http://127.0.0.1:8000`, worker riêng, cùng DB path/environment; CORS cho `http://localhost:5173`. Chạy worker/Chat với clients thật có thể phát sinh phí. VITE_DEMO chỉ là nhãn; fake engines do backend offline launcher inject.

## Chọn môn theo kỳ

- Backend cung cấp `semester_map` từ root `semestermap.json`; frontend không giữ bản sao mapping.
- Kỳ1–4 chung; chọn COMBO để xem kỳ5–9. Có đúng Applied Data Science / AI application.
- Chọn môn kỳN tự chọn toàn bộ kỳ trước; chọn cả kỳN chọn toàn bộ1–N. Bỏ môn kỳN bỏ các kỳ sau; bỏ cả kỳN bỏ N trở đi.
- Đổi COMBO thay các môn riêng tương ứng, giữ môn chung và phạm vi kỳ. Checkbox kỳ hiển thị trạng thái mixed khi chọn một phần.
- Các mã ngoài nguồn đối chiếu vẫn chọn bình thường, không thêm cờ/cảnh báo riêng. Tất cả mã đã chọn được lưu, chỉ tập có nguồn được dùng nội bộ.
- `selection.ts` quản lý quy tắc bằng pure transitions; trạng thái checkbox/count được derive, không đồng bộ bằng effect. Effect checkbox chỉ cập nhật native indeterminate property.

## Contract và bảo vệ nguồn

API `/selections` thay `/clo-sets`; session body dùng `selection_id`. Evidence chỉ có `course_code`; comparison CWA type là `career_comparison`, gồm overview, related_content, gaps, conclusion và radar (kết quả cũ có thể thiếu/null); mỗi finding giữ title/comment/evidence, không có coverage. Radar có overall_score/overall_comment và đúng 5 axes với name/description/score/comment/evidence. JD giữ type `course_jd_comparison`, với radar tùy chọn trong response để đọc được phiên cũ; generation mới có radar khi có yêu cầu chuyên môn để đối chiếu. Session nhận đúng một `career_profile_id` hoặc `job_description`, trả `target` cùng snapshot CWA đã cố định. Frontend types không có mô tả/identifiers của nguồn học phần nội bộ. `/career-profiles` cung cấp tám lựa chọn nghề từ sáu hồ sơ CWA công khai để chọn vị trí và xem mô tả. CWA là tab mặc định; ArrowLeft/Right, Home/End điều hướng tabs, đổi tab giữ bản nháp. Không fetch course detail trước submit hoặc render source; không dùng raw HTML cho Chat.

Vite fs allowlist chỉ có thư mục frontend; file nguồn ở root/data không được phục vụ qua `/@fs/`. Production chỉ publish `dist/` và public API. Việc giữ bí mật dựa vào cả public DTO/projection ở backend, ngữ cảnh Chat và generation validation; ẩn UI riêng lẻ không đủ.

## Request lifecycle và reload

Phần **Khóa học gợi ý** đặt ngay sau tổng quan/radar cho cả CWA và JD. Mount/reload chỉ GET `/advisor/sessions/{id}/recommendations`; bấm nút mới POST body rỗng kèm capability và stable key. Trạng thái chờ/tìm được poll độc lập với comparison; có thể tạm dừng theo dõi mà không hủy job. Mất response giữ key trong workspace để replay; key khác vẫn nhận job cũ. Một bộ tối đa năm khóa được lưu cho phiên, hiển thị tên/link, thông tin có nguồn, lý do và các khoảng trống liên quan; metadata `null` không tạo nhãn giả. Snippet có chú thích giới hạn. Chat giải thích bộ đã lưu, không tìm web; native details hỗ trợ keyboard. Demo giả lập cả nguồn tìm kiếm và link khóa, có nhãn rõ ràng. Xem thêm [ADR 0005](../docs/adr/0005-durable-coursera-suggestions.md).

Trích dẫn `[tên](URL)` và URL thuần trong tổng quan/lý do gợi ý được hiển thị thành link nhúng mở tab mới, áp dụng cả bộ đã lưu mà không tìm lại. Chỉ link Coursera khớp một khóa trong bộ gợi ý được kích hoạt; bỏ query tracking, giữ HTML và link lạ ở dạng text an toàn. Radar CWA không còn đoạn chú thích dưới biểu đồ; chú thích JD, điểm và định nghĩa năm trục giữ nguyên.

- Một submit tạo selection, lưu capability và stable creation key trước khi POST session. Double submit bị khóa bằng ref. StrictMode không tạo thêm generation.
- Poll queued/processing, dừng ready/failed/interrupted, cleanup timer/abort khi rời màn hình.
- “So sánh mục tiêu khác” mở bản nháp mới cho nhóm nghề hoặc JD dùng lại selection/token; chỉ POST khi gửi. Phiên cũ giữ nguyên trong DB.
- Lost response/timeout giữ key/payload; manual replay dùng cùng operation. Không tự đổi key, requeue hoặc POST lại sau reload.
- History chỉ có committed turns. Request bị abort trên browser có thể đã commit ở server; dùng replay cùng key để xác định kết quả.

IDs/token mặc định ở memory. “Giữ phiên trong tab” dùng `skillbridge.course-jd.workspace.v1`, gắn API base; giữ selectionId/token/sessionId, mode và pending payload/key, không giữ nguồn. Phiên JD trong namespace này tiếp tục đọc được; namespace academic cũ bị bỏ qua. JavaScript cùng origin đọc được session storage; đóng tab/xóa state có thể mất capability và không có account recovery.

VITE_* là config công khai: API base, polling2500ms, Chat timeout240000ms, request timeout15000ms, JD100000 chars, message4000 chars. Align với backend overrides; không đưa key vào env frontend.

## Giao diện

CSS semantic tokens tập trung tại `styles.css`. Cam `#F37021`, trắng `#FFFFFF`, xanh lam `#0066B3`, xanh lá `#4EB748`; màu chữ đậm đi cùng nền cam để giữ contrast. Desktop có panel mục tiêu sticky, mobile chuyển một cột. Native checkbox/radio, visible labels/focus, skip link, status text và reduced-motion; màu không là tín hiệu duy nhất.

## Trang kết quả CWA và JD

Kết quả hiển thị theo thứ tự: tổng quan và radar → 5 trục và cách chấm → phân tích chi tiết → Chat. Phần tổng quan dùng tên nghề hoặc mục tiêu JD, số môn của selection và nguyên văn `conclusion`, luôn hiển thị đầy đủ. Hai danh sách “Nội dung liên quan” / “Khoảng trống được ghi nhận” hiện toàn bộ tiêu đề theo thứ tự LLM; không có “Đọc đầy đủ” hoặc “Xem thêm”, không xếp hạng mức quan trọng. Chọn một tiêu đề mở và focus đúng accordion. `overview` nằm trong “Bối cảnh đối chiếu”, không lặp kết luận ở cuối.

Desktop có cột trái chứa toàn bộ nhận định và hai danh sách xếp liền nhau, cột phải chứa điểm tổng và radar, căn trên với chiều cao độc lập. Mobile hiển thị toàn bộ tổng quan trước radar. Giao diện phẳng hơn, giảm viền và khoảng cách; không còn biểu đồ tần suất môn tham chiếu. Môn dẫn chứng vẫn giữ đủ trong phân tích chi tiết và phần 5 trục.

Chi tiết dùng native `details/summary`, mặc định đóng, hỗ trợ Enter/Space, “Mở tất cả / Thu gọn tất cả”. Hai nút chỉ tác động phần phân tích chi tiết; phần 5 trục có thao tác đóng/mở riêng. Tiêu đề, giải thích và evidence giữ nguyên; những mục cùng tiêu đề vẫn độc lập. Khi kết quả sẵn sàng, focus chuyển tới tiêu đề kết quả. CWA và JD dùng chung `ComparisonView`. JD vẫn giữ thứ tự và trạng thái từng yêu cầu; summary nhóm covered/related vào nội dung liên quan, not_evidenced vào khoảng trống. Chi tiết giữ nguyên cả ba trạng thái, giải thích và dẫn chứng; không nhân bản nội dung hoặc tính điểm từ các nhóm này. Chat giữ luồng hiện có. Không gọi thêm inference khi đổi bố cục hoặc mở nội dung.

## Radar đối chiếu theo mục tiêu

Điểm tổng hiển thị lớn nhất trên radar; tổng và từng trục dùng cùng thang 0–5, format tối đa một chữ số thập phân. Frontend dùng trực tiếp điểm tổng của LLM, không tính trung bình, tổng các trục, tỷ lệ references hoặc phần trăm.

Năm tên trục, thứ tự và mô tả phạm vi của CWA được cố định theo vị trí đã chọn và ghim trong phiên (theo ADR 0004); các trục của JD là động do LLM xác định theo yêu cầu tuyển dụng. SVG có 5 đường trục, lưới thang điểm, nhãn và dữ liệu cho screen reader. Phần “Xem 5 trục và cách chấm” nằm riêng ngay trước “Đọc sâu hơn”, mặc định mở, trình bày từng hàng và có thể thu gọn bằng keyboard. Tên, phạm vi, giải thích và môn tham chiếu được giữ đầy đủ; tên dài chỉ rút gọn trên hình. Không thêm thư viện chart.

Phiên cũ thiếu radar hiển thị thông báo trung tính, không giả lập điểm 0 hay POST lại để sinh điểm. Phiên đã có radar giữ nguyên các trục và điểm đã lưu. Radar chỉ có trong kết quả comparison mới sau khi API/worker đã cập nhật. Điểm không phải đo năng lực cá nhân, chất lượng đào tạo hay điểm do CWA quy định; không so sánh trực tiếp điểm giữa các nghề hoặc JD có trục khác nhau. JD không có yêu cầu nội dung để đối chiếu có thể không có radar; giao diện giữ thông báo trung tính.

## Font tại chỗ

Toàn app dùng Noto Sans với các trọng lượng 400/500/600/700, phục vụ từ `public/fonts/` dưới dạng WOFF2. Font có ký tự tiếng Việt, `font-display: swap` và preload bản Regular; không gọi dịch vụ font bên ngoài. Bản build bao gồm font và [giấy phép SIL OFL 1.1](public/fonts/OFL.txt). Assets được chuyển định dạng từ gói `fonts-noto-core` cục bộ, không thêm dependency runtime hoặc build.
