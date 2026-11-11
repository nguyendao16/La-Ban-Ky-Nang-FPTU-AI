# Hướng dẫn chạy live — La Bàn Kỹ Năng

Chạy live trên máy local cần **3 terminal: API, worker và frontend**. Comparison, Chat và nút gợi ý Coursera sẽ gọi OpenAI thật, có phát sinh phí.

**1. Chuẩn bị cấu hình** — tại thư mục gốc repo:

```bash
.venv/bin/python -m pip install -r requirements.txt
cp -n .env.example .env.local
```

Mở `.env.local`, điền:

```dotenv
OPENAI_API_KEY=your_actual_key
```

Giữ các cấu hình model, DB và curriculum mapping trong file mẫu. Không ghi đè `.env` hiện có hoặc đưa API key vào frontend.

**2. Terminal A — chạy API** tại root:

```bash
set -a
source .env.local
set +a

.venv/bin/python -m uvicorn app.main:app \
  --host 127.0.0.1 --port 8000
```

**3. Terminal B — chạy worker** tại root:

```bash
set -a
source .env.local
set +a

.venv/bin/python -m app.jobs.worker_cli
```

API và worker phải dùng cùng `.env.local` để truy cập cùng DB.

**4. Terminal C — chạy frontend**:

```bash
source "$HOME/.nvm/nvm.sh"
nvm use 24

cd frontend
cp -n .env.example .env.local
npm ci
npm run dev -- --host localhost --port 5173 --strictPort
```

Trong `frontend/.env.local`, bảo đảm:

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_DEMO=false
```

Mở **http://localhost:5173** → chọn kỳ/môn → chọn nhóm nghề CWA → **Khám phá nhóm nghề** → chờ kết quả → Chat. Tích **Giữ phiên trong tab** nếu muốn reload và khôi phục phiên.

Với kết quả CWA hoặc JD đã ready, phần **Khóa học gợi ý** ở ngay sau tổng quan/radar có nút **Gợi ý khóa học**. Chỉ bấm nút mới xếp hàng; worker Terminal B xử lý cả comparison và gợi ý, không cần một worker riêng khác. Mỗi phiên lưu tối đa năm khóa/chương trình và không tự tìm lại khi reload. Chat giải thích bộ đã lưu; nếu gợi ý lỗi, comparison và lịch sử vẫn còn. Nếu mất response, giữ nguyên key và dùng **Thử lại cùng yêu cầu gợi ý**; **Tải lại trạng thái gợi ý** chỉ GET. Không tạo phiên mới hoặc đổi key để né trạng thái inference chưa xác định.

Bước gợi ý dùng model/settings review hiện có, yêu cầu model và tài khoản hỗ trợ Responses `web_search`; không tự nâng model. Chưa xác minh live sự kết hợp structured output, URL citations và model/key thực tế trong đợt triển khai offline. Nếu API không trả title/URL citations đủ cho từng khóa, kết quả bị từ chối thay vì đoán link hoặc gọi thêm LLM. Snippet được phép nhưng không xác nhận đầy đủ giáo trình; thông tin chưa có căn cứ được để trống. Xem thêm [ADR 0005](adr/0005-durable-coursera-suggestions.md).

**Áp dụng bản Coursera:** đợi operation đang chạy hoàn tất, dừng API và tất cả worker cũ, sao lưu DB khi đã dừng, rồi khởi động lại cả API/worker bằng code mới. Startup nâng DB CLO–JD schema 1 đúng application ID lên schema 2 trong transaction, giữ snapshot, scores, fingerprints, history, requests và ownership cũ; không reset hoặc sửa file nguồn. DB academic vẫn bị từ chối. Không chạy worker cũ cùng schema mới hoặc tự hạ schema; khi phục hồi bản sao lưu cần dùng phiên bản code tương ứng. Các phiên đã có comparison có thể bấm tìm khóa lần đầu ngay, không cần chấm lại.

Kiểm tra trạng thái tại **http://127.0.0.1:8000/api/v1/health**. Nếu phiên đứng ở `queued`, kiểm tra terminal worker. Khi mất kết nối, dùng **Thử lại cùng yêu cầu**, giữ nguyên key để tránh tạo inference mới.

Khả năng truy cập model và quota phụ thuộc API key của bạn; các lệnh live sử dụng clients thật.

**Khi comparison báo lỗi:** “Tải lại trạng thái” chỉ GET lại phiên; không tạo generation mới. Worker cập nhật sẽ lưu các mã nguyên nhân an toàn như `model_output_limit`, `invalid_structured_output`, `invalid_evidence`, `invalid_coverage`, `private_source_disclosure` hoặc lỗi quota/xác thực. Thông báo trên web diễn giải các mã này; không hiển thị raw response hoặc exception. Job cũ chỉ có `generation_failed` không thể khôi phục nguyên nhân chi tiết từ DB.

`storage_integrity_error` báo worker không xác thực được dữ liệu phiên; chưa đủ để kết luận dữ liệu bị hỏng. Trước tiên kiểm tra API và **mọi worker đang sống** có cùng phiên bản code và cùng cấu hình `.env.local`. Một worker cũ vẫn có thể tranh lấy job mới và từ chối snapshot/fields mới trước khi gọi OpenAI. Chỉ mở thêm worker mới hoặc restart API sẽ không loại bỏ worker cũ. Đợi các operation đang chạy kết thúc, dừng toàn bộ worker cũ rồi khởi động lại bằng cấu hình ở Terminal B. Không sửa snapshot/fingerprint để vượt kiểm tra, không reset DB. Nếu `dispatched_at` còn null, job đã thất bại trước bước dispatch; chỉ requeue đúng job sau khi nguyên nhân được xử lý và lượt inference được cho phép.

Sau cập nhật bảo mật đầu ra, khởi động lại API và tất cả worker khi không có operation đang chạy. API mới lọc nội dung nội bộ trong kết quả/history cũ khi tải lại hoặc replay; không cần chấm lại hay reset DB. Comparison mới dùng prompt bảo mật và guard trước commit; Chat cũng dùng kết quả/history đã lọc. Mã `private_policy_disclosure` báo phản hồi không vượt qua kiểm tra nội dung riêng tư; lỗi được lưu bằng thông điệp an toàn, không kèm đoạn vi phạm. Operation bị từ chối sẽ rollback, không tự chạy thêm LLM. `invalid_structured_output` vẫn có thể là điểm tổng vượt trục cao nhất. Xem thêm [kiến trúc bảo mật đầu ra](architecture.md#3-ranh-giới-dữ-liệu-máy-chủ-và-hợp-đồng-công-khai-server-source-vs-public-dto-boundary).

Operator kiểm tra `comparison_job.error_code` và log worker trước. Chỉ sau khi quyết định chạy lại và chấp nhận khả năng phát sinh thêm phí, dùng cùng cấu hình ở root:

```bash
.venv/bin/python -m app.jobs.worker_cli --retry-job <job_id> --acknowledge-possible-duplicate
.venv/bin/python -m app.jobs.worker_cli --once
```

Lệnh đầu chỉ đưa đúng job trở lại queue, giữ snapshot và lịch sử recovery. Lệnh `--once` lấy job đầu queue; xác nhận đúng job cần xử lý và không có worker khác trước khi dùng cho một lần kiểm tra có kiểm soát. Không đổi idempotency key hoặc tạo phiên mới để né trạng thái lỗi. Không tự tăng token budget/timeout khi chưa biết nguyên nhân.

Sau cập nhật bộ trục CWA, khởi động lại API và tất cả worker khi không có operation đang chạy, rồi tạo phép so sánh mới. Catalog có tám lựa chọn; ML, CV và NLP/LLM dùng chung hồ sơ nguồn nhưng có phạm vi và năm trục riêng. Tên tiếng Anh/thứ tự/mô tả tiếng Việt được ghim theo phiên; điểm tổng chỉ xét trong năm trục. Không đổi tên trục hoặc chấm lại phiên cũ; không reset DB. `invalid_structured_output` cũng có thể báo output đổi tên, thứ tự hoặc mô tả trục; job rollback và không tự gọi lại. JD tiếp tục dùng trục động như trước. Xem thêm [ADR 0004](adr/0004-fixed-cwa-target-axes.md).
