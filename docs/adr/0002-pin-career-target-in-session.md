# Cố định hồ sơ nhóm nghề trong snapshot phiên

Session CWA lưu toàn bộ bản nội dung đã xác thực tại lúc tạo, với fingerprint và format version 4, thay vì chỉ lưu ID rồi đọc file khi worker chạy. Cách này giúp kết quả, Chat và replay cùng tham chiếu một bản tài liệu dù catalog thay đổi; ID nhóm nghề tham gia idempotency, còn snapshot đã nhận được giữ nguyên. Session JD version 3 vẫn dùng contract riêng và cùng cơ chế SQLite/queue/fencing, không chuyển hồ sơ CWA thành JD giả hoặc tự migrate phiên cũ.
