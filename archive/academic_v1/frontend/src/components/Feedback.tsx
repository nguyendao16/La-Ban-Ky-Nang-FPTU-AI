import { ApiError } from "../api";
const messages: Record<string, string> = {
  invalid_scores: "Điểm chưa hợp lệ. Kiểm tra môn học và assessments bên dưới.",
  invalid_request: "Dữ liệu gửi lên chưa hợp lệ.",
  invalid_input: "Nội dung không hợp lệ hoặc vượt giới hạn.",
  unauthorized:
    "Thiếu quyền truy cập phiên. Capability chỉ được cấp khi tạo hồ sơ.",
  access_denied: "Bạn không có quyền truy cập hồ sơ hoặc phiên này.",
  session_not_ready: "Initial Review chưa sẵn sàng. Hãy chờ worker hoàn tất.",
  session_busy:
    "Phiên đang xử lý một thao tác khác. Thử lại với cùng yêu cầu sau khi thao tác đó hoàn tất.",
  operation_running:
    "Yêu cầu này vẫn đang chạy. Thử lại sau để lấy kết quả với cùng mã thao tác.",
  operation_interrupted:
    "Thao tác đã bị gián đoạn; kết quả inference có thể chưa xác định. Cần operator kiểm tra, không tự gửi lại thành thao tác mới.",
  operation_failed:
    "Thao tác không hoàn tất. Không có câu trả lời mới được lưu; cần kiểm tra phiên trước khi tiếp tục.",
  idempotency_conflict:
    "Mã thao tác đã gắn với nội dung khác. Yêu cầu chưa được gửi lại.",
  backend_unavailable:
    "Backend chưa sẵn sàng. Kiểm tra cấu hình API và worker.",
  storage_unavailable: "Kho dữ liệu tạm thời không sẵn sàng.",
  course_data_unavailable: "Dữ liệu môn học chưa đủ để tạo hồ sơ.",
  unknown_course: "Môn học không thuộc curriculum đang dùng.",
  transport_timeout:
    "Hết thời gian chờ. Backend có thể vẫn đang xử lý; thử lại cùng yêu cầu để lấy kết quả, không tạo thao tác mới.",
  network_error:
    "Mất kết nối. Kết quả chưa xác định; thử lại cùng yêu cầu khi mạng ổn định.",
  invalid_response:
    "Backend trả dữ liệu không đọc được. Giữ nguyên yêu cầu nếu cần thử lại.",
};
export const canReplay = (error: unknown) =>
  error instanceof ApiError &&
  [
    "transport_timeout",
    "network_error",
    "invalid_response",
    "operation_running",
    "session_busy",
    "backend_unavailable",
    "storage_unavailable",
    "internal_error",
    "http_error",
  ].includes(error.code);
export function Feedback({ error }: { error: unknown }) {
  if (!error || (error instanceof ApiError && error.code === "cancelled"))
    return null;
  const details =
    error instanceof ApiError && Array.isArray(error.details)
      ? error.details
      : [];
  return (
    <div className="notice error" role="alert">
      <p>
        {error instanceof ApiError
          ? messages[error.code] ||
            "Thao tác không thành công. Kiểm tra dữ liệu và trạng thái phiên."
          : typeof error === "string"
            ? error
            : "Không thể hoàn tất thao tác."}
      </p>
      {details.length > 0 && (
        <ul>
          {details.map((d, i) => (
            <li key={i}>
              {[d.course_code, d.category, d.issue || d.type]
                .filter(Boolean)
                .join(" · ")}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
export function Loading({ children }: { children: React.ReactNode }) {
  return (
    <p className="loading" role="status">
      <span className="spinner" aria-hidden="true" />
      {children}
    </p>
  );
}
