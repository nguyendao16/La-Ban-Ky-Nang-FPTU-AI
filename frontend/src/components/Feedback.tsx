import { ApiError } from "../api";
const messages: Record<string, string> = {
  invalid_selection:
    "Lựa chọn môn chưa hợp lệ. Kiểm tra các ràng buộc bên dưới.",
  invalid_request: "Dữ liệu gửi lên chưa hợp lệ.",
  invalid_input: "Nội dung không hợp lệ hoặc vượt giới hạn.",
  unauthorized:
    "Không tìm thấy quyền truy cập phiên. Hãy dùng phiên đã lưu hoặc chọn môn để bắt đầu lại.",
  access_denied: "Bạn không có quyền truy cập lựa chọn môn hoặc phiên này.",
  session_not_ready: "Kết quả chưa sẵn sàng. Vui lòng chờ xử lý hoàn tất.",
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
  course_data_unavailable:
    "Chưa thể xử lý các môn đã chọn. Vui lòng thử lại sau.",
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

const comparisonReasons: Record<string, string> = {
  storage_integrity_error:
    "Dữ liệu phiên không vượt qua kiểm tra tính hợp lệ. Cần kiểm tra phiên bản API/worker và dữ liệu đã lưu.",
  model_output_limit:
    "Phân tích đạt giới hạn độ dài phản hồi nên chưa hoàn tất.",
  model_response_incomplete: "Dịch vụ AI trả về phản hồi chưa hoàn tất.",
  model_refusal: "Dịch vụ AI từ chối xử lý yêu cầu này.",
  missing_structured_output:
    "Dịch vụ AI chưa trả về kết quả phân tích có thể sử dụng.",
  invalid_response_status: "Dịch vụ AI chưa hoàn tất phản hồi phân tích.",
  invalid_structured_output:
    "Kết quả phân tích chưa đúng định dạng nên chưa được lưu.",
  invalid_evidence:
    "Dẫn chứng trong kết quả phân tích chưa hợp lệ nên chưa được lưu.",
  invalid_coverage:
    "Nhận định và dẫn chứng chưa nhất quán nên kết quả chưa được lưu.",
  private_source_disclosure:
    "Kết quả phân tích chưa đáp ứng yêu cầu bảo vệ dữ liệu nên chưa được lưu.",
  private_policy_disclosure:
    "Kết quả phân tích chưa đáp ứng yêu cầu bảo vệ dữ liệu nên chưa được lưu.",
  context_limit:
    "Nội dung yêu cầu vượt giới hạn xử lý của model đang cấu hình.",
  authentication_failed:
    "Dịch vụ AI chưa xác thực được. Cần kiểm tra cấu hình worker.",
  quota_exhausted:
    "Dịch vụ AI đã hết hạn mức sử dụng. Cần kiểm tra quota hoặc billing.",
  rate_limited: "Dịch vụ AI đang vượt giới hạn số yêu cầu.",
  upstream_api_error:
    "Dịch vụ AI không tiếp nhận được yêu cầu. Cần kiểm tra cấu hình hoặc quyền truy cập model.",
  configuration_or_input_error:
    "Chưa thể bắt đầu phân tích. Cần kiểm tra cấu hình worker và dữ liệu phiên.",
};

export function ComparisonFailure({ code }: { code?: string | null }) {
  return (
    <div className="notice error" role="alert">
      <p>
        {comparisonReasons[code ?? ""] ??
          "Phân tích không hoàn tất; phiên này chưa có nguyên nhân lỗi chi tiết."}
      </p>
      <p>
        Tải lại trạng thái chỉ kiểm tra phiên hiện tại. Cần operator kiểm tra
        trước khi chạy lại; ứng dụng không tự gửi thêm lượt phân tích.
      </p>
    </div>
  );
}

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
