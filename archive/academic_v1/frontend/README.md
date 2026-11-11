# SkillBridge frontend local

React + TypeScript + Vite, không có router/global state library. API calls ở `src/api.ts`; DTOs ở `src/types.ts` mirror `app/schemas`. Backend là nguồn cho courses, assessments, scores, achievement, Review và evidence.

## Cài đặt và kiểm tra

Node >=22.12. Môi trường verification dùng Node 24.16.0 qua NVM; nếu shell chưa có `node`:

```bash
source "$HOME/.nvm/nvm.sh"
nvm use 24
cd frontend
npm ci
npm test
npm run build
npm exec playwright install chromium
npm run test:e2e
```

Playwright tự start disposable offline API/fake worker và Vite, dừng/xóa DB khi hoàn tất. Cần ports 8001/5173 trống. Tests không chạy worker thật hoặc OpenAI. `test:e2e` chạy desktop và mobile, gồm mất response sau Chat commit, replay cùng key, hai turns, browser reload và xác nhận một Review attempt.

## Demo offline tương tác

Terminal A, tại root:

```bash
.venv/bin/python -m examples.offline_demo
```

Terminal B:

```bash
cd frontend
VITE_API_BASE_URL=http://127.0.0.1:8001 VITE_DEMO=true npm run dev
```

Mở `http://localhost:5173`. Catalog/assessments/scoring dùng dữ liệu thật. Review/Chat có nhãn **DEMO OFFLINE**, luôn giả lập. Launcher giữ API và worker ở processes riêng, dùng SQLite trong temporary directory được đánh dấu; Ctrl+C dừng cả hai và xóa DB. Không cần `.env` hay API key. Nếu đổi `--port`, đổi `VITE_API_BASE_URL` tương ứng. CORS demo chỉ cho `http://localhost:5173`.

Chọn ADY201m → nhập 8 điểm → tạo profile 7 CLOs → bật lưu tab nếu cần reload → dán JD → tạo phiên → chờ Review → gửi nhiều câu hỏi → tải lại history. Điểm 0 hợp lệ; ô trống bị từ chối. Mock outputs không kiểm chứng chất lượng LLM.

## Local với inference thật: ba terminals

Tại root, tạo config riêng **không ghi đè `.env`**:

```bash
cp -n .env.example .env.local
```

Điền `OPENAI_API_KEY` trong file local hoặc process environment. `.env.local` bị gitignore. Candidate configuration trong example được opt-in khi source file; defaults global vẫn giữ nguyên. Không chạy worker thật để smoke test queue đang có dữ liệu.

Terminal A — API, root:

```bash
set -a
source .env.local
set +a
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Terminal B — worker, root:

```bash
set -a
source .env.local
set +a
.venv/bin/python -m app.jobs.worker_cli
```

Worker này có thể phát sinh **phí OpenAI** khi xử lý queued Review. POST Chat cũng inference thật. API không tự start worker. Hai processes phải dùng cùng `SKILLBRIDGE_DATABASE_PATH`; relative path được tính từ working directory, nên luôn chạy tại root. CORS allowlist example là `http://localhost:5173`; không dùng `*`.

Terminal C — frontend:

```bash
cd frontend
cp -n .env.example .env.local
npm ci
npm run dev
```

`VITE_API_BASE_URL` mặc định `http://127.0.0.1:8000`. Vite chỉ dùng biến `VITE_*` cho browser bundle; **không đặt API key/capability vào frontend env**. Chat timeout mặc định 240.000 ms tương ứng backend 180s +60s overhead; tăng `VITE_CHAT_TIMEOUT_MS` nếu tăng backend timeout. Polling mặc định 2.500 ms. Giới hạn JD/message mặc định 100.000/4.000 ký tự; chỉnh frontend phù hợp nếu backend dùng limits riêng, backend luôn validate cuối cùng.

Alias `source-3173` chỉ phản ánh source curriculum ID có thật; chưa có authoritative evidence cho nhãn `BIT_AI_K20C`. Không hardcode catalog trong UI. Backend cần mapping/default curriculum tường minh trước startup.

## Capability, retries và history

- Mặc định token/IDs ở React state, không lưu browser storage. Reload trang sẽ mất quyền truy cập; có thể tải lại history qua nút trong UI khi state còn nguyên.
- Opt-in **Giữ phiên trong tab** lưu token, profile/session IDs và pending JD/Chat payload + idempotency key trong session storage. State gắn với API base URL và tab; đóng tab/xóa state mất capability. JavaScript cùng origin đọc được storage, nên đây không phải kho secret chống XSS. UI render text bằng React, không inject HTML từ LLM.
- Một logical JD/Chat operation tạo một UUID key trước dispatch. Retry do transport timeout/network failure/operation running dùng lại key và payload đó. Không automatic POST retry. Busy disable và synchronous ref guard ngăn double-submit.
- Pending payload được khóa khi kết quả chưa biết. `failed/interrupted` Review cần operator, không tự queue lại. Chat interrupted không chuyển sang key mới và không fabricate reply. Timeout có thể chỉ là client hết thời gian chờ; backend vẫn có thể commit.
- Poll GET chạy một loop; cleanup abort khi rời view, dừng ở ready/failed/interrupted. Không hiển thị progress percentage.
- History chỉ nhận committed turns từ API, giữ `message_id`, thứ tự, reply/evidence. Reload tab opt-in chỉ GET profile/status/history; không tạo Review/Chat mới. Hồ sơ đã gắn session không bị mutate khi bắt đầu hồ sơ mới.

## Phạm vi

Đủ luồng local MVP, không có accounts/OAuth/token recovery, streaming, public deployment, aggregate skill/employability score hoặc Coursera/search clients. Chat vẫn synchronous, giữ giới hạn turns hiện có. Interrupted operation cần operator CLI; UI không có quyền requeue. In-memory sessions không khôi phục được sau browser reload nếu chưa opt-in lưu tab.
