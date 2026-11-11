# Radar năm trục do LLM xác định trong cùng lần đối chiếu

Ngày 19/10/2026: phần LLM tự xác định tên/phạm vi trục CWA được thay thế bởi [ADR 0004](0004-fixed-cwa-target-axes.md); JD vẫn dùng trục động. Các nguyên tắc chấm, bảo mật và bảo toàn kết quả cũ bên dưới tiếp tục áp dụng.

Theo yêu cầu mới, mỗi comparison CWA mới sinh đúng năm trục theo nhóm nghề, gồm tên, phạm vi nội dung, điểm 0–5, giải thích và evidence trong cùng một response với phân tích hiện có. Điểm tổng là nhận định trực tiếp của LLM, có giải thích riêng, thay vì trung bình hoặc tổng điểm các trục; đây là điểm đối chiếu nội dung do ứng dụng cung cấp, không phải thang điểm chính thức của CWA hay phép đo năng lực cá nhân. Phiên cũ không có radar tiếp tục đọc được với nguyên fingerprints, không tự thêm điểm, đổi key hoặc chạy lại inference.

Cập nhật ngày 18/10/2026: JD và CWA dùng chung hướng dẫn chấm chặt hơn, với năm trục xác định từ toàn bộ mục tiêu trước khi xét các môn. Điểm tổng vẫn do LLM chọn trực tiếp, nhưng kết quả mới không được vượt trục cao nhất; tổng dương cần trục dương có evidence hợp lệ. Thang hỗ trợ nội dung và trần 2/5, 3/5 được quy định trong prompt. Giữ nguyên schema theo lựa chọn của người dùng, nên backend không kiểm tra các trần mang ý nghĩa ngữ nghĩa này. Đường đọc snapshot cũ giữ chính sách cũ; không thêm version, migrate hoặc chấm lại. [Quy tắc và giới hạn](../../app/engines/prompts.py).

## Thay thế điểm thuần nội dung cho kết quả mới — 18/10/2026

Người dùng mở lại quyết định và chọn để kinh nghiệm ảnh hưởng cả tổng lẫn năm trục, thay cho việc chỉ nêu riêng kinh nghiệm. Kết quả mới là **điểm phù hợp theo bối cảnh**: đối chiếu nội dung/độ sâu với mục tiêu dưới giả định sinh viên có dưới một năm kinh nghiệm; không xác nhận năng lực hoặc khả năng được tuyển. Chỉ điều kiện số năm kinh nghiệm bắt buộc, có nêu rõ mới kích hoạt trần kinh nghiệm, theo đúng phạm vi trục. Không tự gán ngưỡng năm cho CWA. Các trần độ sâu 1/2, tổng lõi tối đa 2 và kinh nghiệm 3/2/1 thay hướng dẫn trước; lấy giới hạn thấp nhất, không cộng dồn khoản trừ.

Trade-off được chấp nhận: giữ schema và một generation nên các trần ngữ nghĩa vẫn do LLM tuân thủ trong prompt, backend tiếp tục chỉ xác thực số học/evidence. Lý do và giả định dùng các trường prose hiện có. UI dùng nhãn trung tính và chỉ hiển thị giả định được lưu trong từng kết quả; Chat không áp lại quy tắc mới cho phiên cũ. Snapshot, điểm, fingerprints và lịch sử cũ không đổi; không suy phiên bản policy từ prose hoặc thêm migration. [Phạm vi và kiểm thử](../../tests/test_stricter_scoring.py).

## Giữ quy tắc chấm và giả định trong nội bộ — 18/10/2026

Theo quyết định mới của người dùng, yêu cầu công khai giả định/cách điều kiện giới hạn điểm ở phần trên được thu hồi. Cách chấm và các trần vẫn áp dụng trong nội bộ. Phần công khai chỉ giải thích quan hệ nội dung, độ sâu và yêu cầu thực sự của mục tiêu; không nêu giả định về người dùng hoặc liên hệ một điều kiện với việc điều chỉnh điểm. Không bịa ra khoảng trống chuyên môn để thay cho lý do chấm nội bộ.

Generation mới được kiểm tra trước commit; phát hiện mẫu tiết lộ thì rollback, không tự gọi thêm LLM. Dữ liệu cũ tiếp tục xác thực bằng bản gốc; lớp public projection lọc các field bị nhận diện trước khi trả API hoặc đưa vào Chat. DB, điểm và fingerprints không đổi. Trade-off: guard dựa trên mẫu và đoạn trùng prompt có thể bỏ sót diễn đạt khác hoặc từ chối nhầm; không phải chứng minh bí mật tuyệt đối. [Phạm vi và kiểm thử](../../tests/test_policy_privacy.py).
