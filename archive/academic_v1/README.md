# SkillBridge V1 Academic Knowledge Review

Component Python nhận Student Academic Profile và Job Description (JD), tạo nhận xét học thuật bằng tiếng Việt rồi xác thực các tham chiếu CLO. Review mô tả những nội dung được học và kết quả học thuật liên quan đến JD; dữ liệu này không xác nhận kinh nghiệm làm việc hoặc năng lực triển khai trong môi trường nghề nghiệp.

## Frontend MVP và demo offline

`frontend/` dùng React, TypeScript và Vite, gọi trực tiếp chín API hiện có. Luồng: chọn môn/COMBO → nhập assessments 0–10 → hồ sơ CLO → JD → poll Initial Review → Chat nhiều lượt. Definitions, scores, achievement và evidence lấy từ backend; frontend không tính lại CLO hoặc matching score.

Demo an toàn, terminal A tại root repository:

```bash
.venv/bin/python -m examples.offline_demo
```

Launcher tạo SQLite tạm và hai child processes riêng cho API `127.0.0.1:8001` và fake worker. Review/Chat luôn được inject mocks, không cần OpenAI key, không dùng DB của sinh viên. Ctrl+C dừng processes và xóa DB tạm. Terminal B:

```bash
# Node >=22.12; môi trường hiện tại có Node 24 qua NVM.
source "$HOME/.nvm/nvm.sh"
nvm use 24
cd frontend
npm ci
VITE_API_BASE_URL=http://127.0.0.1:8001 VITE_DEMO=true npm run dev
```

Mở `http://localhost:5173`, chọn ADY201m, nhập đủ 8 assessments (0 hợp lệ), tạo hồ sơ, dán JD, chờ Review và gửi Chat. Mặc định capability ở bộ nhớ; bật **Giữ phiên trong tab** nếu muốn reload trang và đọc lại committed history. Tùy chọn này lưu capability/IDs và pending payload/key trong session storage cùng origin; JavaScript cùng origin đọc được, nên chỉ dùng trên máy tin cậy. Không ghi token vào URL, console hoặc source. Đóng tab/xóa state sẽ mất capability; backend chưa có token recovery. Trong demo, dừng launcher cũng xóa DB.

[Hướng dẫn frontend](frontend/README.md) có cấu hình API thật, ba terminals, token/idempotency policy và lệnh kiểm thử. [Báo cáo readiness tiếng Việt](docs/backend_frontend_integration_readiness.vi.md) ghi baseline/final counts, SDK audit, integrity và kết quả browser flow.

## FastAPI, SQLite và Review worker

Backend hiện cung cấp chín endpoints dưới `/api/v1`: courses, profiles, Advisor sessions, messages và health. SQLite lưu immutable profiles, session snapshots v2, history, idempotency records và Review jobs. API không dùng file JSON làm kho authoritative thứ hai; các CLI/file sessions vẫn hoạt động như trước.

```bash
.venv/bin/python -m pip install -r requirements.txt

# Alias tường minh theo source ID; không khẳng định BIT_AI_K20C = 3173.
export SKILLBRIDGE_CURRICULUM_MAPPING='{"source-3173":"3173"}'
export SKILLBRIDGE_DEFAULT_CURRICULUM=source-3173
export SKILLBRIDGE_DATABASE_PATH="$PWD/var/skillbridge.sqlite3"
export SKILLBRIDGE_CORS_ORIGINS='["http://localhost:5173"]'

.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# Trong terminal khác, export cùng infrastructure configuration:
.venv/bin/python -m app.jobs.worker_cli --review-timeout 360
```

Infrastructure variables được đọc từ process environment; export chúng hoặc dùng `uvicorn --env-file` nếu cần. OpenAI settings tiếp tục dùng `load_settings()` và `.env`/environment precedence hiện có. Listing courses, building profiles và queueing sessions không cần API key. Worker khi claim Review, hoặc API khi chạy Chat thật, mới cần credentials. Worker/POST Chat thật có thể phát sinh phí; các tests/examples dưới đây chỉ dùng mocks. Không khởi động worker trong FastAPI lifespan.

`POST /profiles` trả `profile_id`, enriched profile, diagnostics và một capability `access_token`. Giữ token ở client một cách an toàn; gửi `Authorization: Bearer <token>` khi GET profile hoặc dùng sessions của profile đó. SQLite chỉ lưu hash token. Token không nằm trong URL; không có account/token recovery. UUID đơn thuần không đủ quyền đọc dữ liệu.

`POST /advisor/sessions` và `POST /advisor/sessions/{id}/messages` yêu cầu `Idempotency-Key`. Giữ nguyên key khi retry cùng request. Session creation trả `202 queued`; worker riêng xử lý Review. GET session đọc persisted state và không chờ inference lock. Cùng session đang có operation trả `409`; khác sessions có thể chạy đồng thời. Reply giữ evidence schema cũ; `message_id` chỉ nằm trong HTTP envelope.

Worker claim, heartbeat và commit dùng SQLite owner token, generation và revision. Lease hết hạn được chuyển sang `interrupted`, không tự requeue. Durable snapshot operations tạo SDK clients với **`max_retries=0`** để tránh tự retry dispatch không chắc chắn; CLI/file-session SDK policy cũ không đổi. Nếu inject SDK client thật cho snapshot operations, cấu hình nó tương tự. Model names, reasoning, token budgets, prompts và schemas giữ nguyên; `--review-timeout` là override tường minh cho timeout có sẵn.

```bash
# Một job tối đa; có thể inference thật nếu có queued work:
.venv/bin/python -m app.jobs.worker_cli --once --review-timeout 360
# Chỉ recovery trạng thái, không inference:
.venv/bin/python -m app.jobs.worker_cli --recover-only
# Operator chủ động requeue; lệnh này chưa chạy inference:
.venv/bin/python -m app.jobs.worker_cli --retry-job JOB_ID \
  --acknowledge-possible-duplicate
```

Flag acknowledgement bắt buộc nếu job đã đánh dấu dispatch; remote outcome có thể chưa biết và retry có thể phát sinh generation trùng. Không có exactly-once remote inference qua arbitrary crashes. Chat key interrupted luôn trả uncertainty; client không tự đổi key để rerun. Một key mới biểu thị operation mới được người dùng chủ động yêu cầu.

Chạy toàn bộ HTTP flow offline, với temporary SQLite và categories ADY201m thật:

```bash
.venv/bin/python -m examples.http_integration \
  --curriculum-code source-3173 --curriculum-source-id 3173
.venv/bin/python -m pytest -q
.venv/bin/python -m pip check
```

OpenAPI/Swagger: `/openapi.json` và `/docs`. [Báo cáo triển khai tiếng Việt](docs/fastapi_sqlite_backend_report.vi.md) ghi milestone backend trước frontend. Hiện có frontend local; chưa có OAuth, Redis/Celery, streaming, web search hoặc Coursera integration.

`.env.example` chứa candidate settings tường minh: Review `gpt-5.4/high/32768/360s`, Chat `gpt-5.4-mini/medium/8192/180s`, curriculum alias `source-3173`, SQLite `var/skillbridge.sqlite3` và CORS `http://localhost:5173`. Copy sang `.env.local`, không overwrite `.env` của người dùng. Source cùng file vào process environment của cả API và worker; infrastructure không tự đọc dotenv. `OPENAI_REVIEW_REQUEST_TIMEOUT` / `OPENAI_CHAT_REQUEST_TIMEOUT` được loader hỗ trợ; explicit argument/`--review-timeout` thắng environment, rồi đến defaults cũ. `ReviewSettings.timeout` là property resolved hợp lệ, đọc từ field `request_timeout`; không có lỗi property mismatch.

Xem cấu hình khôngsecret, không cần key hoặc network:

```bash
.venv/bin/python -m app.settings_diagnostics --env-file .env.example
```

## Ba service dùng trực tiếp từ Python

`app.services` cung cấp `CourseService`, `ProfileService`, `AdvisorService`. Các business services trả dict/Pydantic objects và domain exceptions, không phụ thuộc CLI/HTTP. Course/Profile không gọi OpenAI. `ProfileService` không cấp IDs; profile IDs và persistence của HTTP flow thuộc SQLite repositories. `PersistentAdvisor` dùng snapshot operations của AdvisorService cho API/worker, không dùng registry trong bộ nhớ làm persistence.

Catalog dùng `data/stage1/subjects` và `combo_slot_map.json` để xác định membership, tên, semester và COMBO; metadata/CLO/assessments canonical nằm tại `data/courses`. Curriculum source ID hiện có là `3173`; processed records không có nhãn `BIT_AI_K20C`. Caller phải cung cấp mapping và default curriculum tường minh. Không suy từ tên COMBO có chữ K17 thành curriculum của sinh viên.

```python
from app.services import CourseService, ProfileService, GradeEntry, AdvisorService

# Alias dùng cho ví dụ theo source ID, không khẳng định BIT_AI_K20C = 3173.
catalog = CourseService(
    curriculum_mapping={"source-3173": "3173"},
    default_curriculum_code="source-3173",
)
courses = catalog.list_courses()
metadata = catalog.get_course("ADY201m")
assessments = catalog.get_course_assessments("ADY201m")
```

`list_courses()` giữ entries chưa dùng được, kèm `availability` và `diagnostics`; hiện có 49 entries, gồm 20 COMBO alternatives. `AI17_GRA_ELE` chưa có metadata/CLO/assessment dùng được: entry vẫn được liệt kê nhưng Python getters báo domain exception; HTTP detail trả availability và dữ liệu thiếu dưới dạng null. Tất cả getters nhận optional `curriculum_code`, giống listing. `get_selection_constraints()` dựa trên source `combo_slot`/`combo_options`: hai alternatives của cùng một curricular slot bị ProfileService từ chối; thiếu descriptor thì slot được báo ambiguous. Không suy mutual exclusion từ semester hoặc ép chọn cả track. `get_course()` giữ raw metadata/extra fields; `tools` không xác nhận sinh viên đã dùng công cụ.

Assessment identifier là **`category` trong phạm vi từng môn**, không có UUID assessment trong nguồn. Return giữ nguyên `category`, `part`, `weight`, `clo` và thứ tự; ví dụ `weight="20.0%"` không bị đổi thành `0.2`.

```python
import json
from pathlib import Path

grades = json.loads(Path("academic_report.json").read_text(encoding="utf-8"))
profiles = ProfileService(catalog)
profile, validation_report = profiles.build_profile_with_report(
    selected_courses=["ADY201m"],
    assessment_scores={"ADY201m": grades["ADY201m"]},
)

# Dạng entries phát hiện được cả entries trùng cùng category.
entries = [GradeEntry("ADY201m", category, grade)
           for category, grade in grades["ADY201m"].items()]
assert profiles.build_profile(["ADY201m"], entries) == profile
```

`build_profile()` trả profile; `build_profile_with_report()` trả `(profile, report)`; `validate_scores()` trả report hoặc raise `ScoreValidationError` có `.issues` và `.report` (report có thể chưa có nếu cấu trúc input bị từ chối sớm). Cả ba nhận keyword `curriculum_code` để kiểm tra tất cả courses/grades cùng curriculum. Mapping Python đã ghi đè exact duplicate key không thể phục hồi; dùng entries nếu cần kiểm tra duplicates. Scorer vẫn match exact/normalized/spelling aliases hiện có.

Service yêu cầu đủ grades của các assessments canonical, rejects unknown/duplicate entries và scores của môn không được chọn. Missing/null khác zero; zero là điểm hợp lệ. Numeric strings hợp lệ được chấp nhận; boolean, NaN/infinity và grades ngoài 0–10 bị từ chối. CLI legacy vẫn giữ partial scoring: bỏ missing grades khỏi trọng số và dùng `null/not_evaluated` khi CLO không có graded evidence. Hai đường dùng chung công thức scoring; khác biệt nằm ở validation input đã chủ động chọn.

Các diagnostics sẵn có về CLO mapping và weight totals được giữ trong report, không tự sửa canonical data hoặc cách tính. Hiện bảy môn có CLO-mapping diagnostics; hai môn có tổng weights khác 100%. Dùng `build_profile_with_report()` để hiển thị diagnostics cho frontend. Không phương thức build nào tự lưu profile/report hoặc ghi đè các academic files; caller chỉ lưu khi chủ động yêu cầu bằng persistence helper hiện có.

```python
# Chỉ tạo session; không generation và chưa cần API key.
with AdvisorService() as advisor:
    session = advisor.create_session(profile, "JD supplied as plain text")
    assert session.status == "pending_review"
    # Các operation sau gọi engine OpenAI thật nếu không inject mocks:
    # initial_review = advisor.run_initial_review(session.session_id)
    # response = advisor.send_message(session.session_id, "Mình đã học gì liên quan?")
```

Advisor nhận `review_engine`, `chat_session_factory`, clients và `review_settings`/`chat_settings` qua constructor. Mặc định settings dùng `load_settings()` theo stage tại operation; không đổi `.env`, models, prompts, schemas, preflight hoặc SDK retry policy. Candidate Review 32.768 tokens/360 giây cần override `ReviewSettings` tường minh; defaults hiện tại vẫn giữ nguyên. `create_session()`/`resume_session()` không gọi inference. `run_initial_review()` commit một Review, rejects rerun bằng `ReviewAlreadyReadyError`; `send_message()` yêu cầu Review ready (`ReviewNotReadyError`) và không tạo lại Review. Các lỗi engine vẫn là `ReviewError`/`ChatError`; services không gắn HTTP status codes.

`get_session()` trả `AdvisorSessionView` (ID, pending/ready, fingerprints, Review, turn count, persistent); `get_history()` trả bản copy các cặp user/assistant đã commit. `UnknownCurriculumError`, `UnknownCourseError`, `InvalidMetadataError`, `MissingAssessmentDataError`, `InconsistentSourceDataError`, `CourseDataError`, `ScoreValidationError`, `SessionNotFoundError` có thể được API adapter ánh xạ sau này.

`create_session(..., persist=True)` dùng cùng local atomic writer/POSIX locking nhưng lưu snapshot **version 2**: profile, JD nguyên văn, Review tùy chọn, SHA-256 và history. Không lưu API key/settings. Version 1 từ `AcademicChatSession.from_files()` và CLI vẫn nguyên format/path fingerprints; không migrate sessions cũ. `resume_session(id)` dành cho version 2; legacy sessions tiếp tục resume qua CLI/from_files với ba file nguồn. Object caller đổi sau khi tạo session không đổi snapshot. Tampered snapshots hoặc evidence/history không hợp lệ bị từ chối.

Persistence giữ lock đến `close_session(id)`/`close()` hoặc khi rời context manager. Worker tương lai có thể resume pending snapshot sau khi owner ban đầu đóng session; Review vẫn là callable synchronous, chưa thêm queue/background tasks. Registry thuộc mỗi service instance; `get_session()` chỉ đọc session đang được instance đó quản lý. Adapter đa process/storage chung và trạng thái job chi tiết thuộc giai đoạn API sau.

Chạy example hoàn toàn offline với mapping tường minh theo source ID:

```bash
.venv/bin/python -m examples.services_integration \
  --curriculum-code source-3173 --curriculum-source-id 3173
```

Example dùng grades/JD thật hiện có và mocked SDK responses cho Review/Chat, không tạo OpenAI client, không đọc `.env`, không persist files. Muốn dùng nhãn `BIT_AI_K20C`, cần authoritative mapping do người quản lý curriculum cung cấp. Xem [báo cáo refactor](docs/service_refactor_report.vi.md) về architecture và kiểm thử.

## Cài đặt

Chạy từ root của repository với Python 3.10 trở lên:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
source .venv/bin/activate
```

Dependencies gồm OpenAI Python SDK hỗ trợ Responses API và input token counting, Pydantic v2, python-dotenv và pytest. Các phiên bản thực tế đã kiểm thử được ghi trong báo cáo đánh giá.

## Cấu hình OpenAI

CLI tự đọc `.env` tại root, không ghi đè biến môi trường đã có. Dùng cấu hình:

```dotenv
OPENAI_API_KEY=<API key của bạn>
OPENAI_MODEL=gpt-4o-mini
```

`OPENAI_API_KEY` là bắt buộc. Model được chọn theo thứ tự CLI `--model` → `OPENAI_REVIEW_MODEL` hoặc `OPENAI_CHAT_MODEL` → `OPENAI_MODEL` → `MODEL` → `gpt-4o-mini`. `.env` hiện dùng `MODEL` vẫn hoạt động; `.env.example` cung cấp tên biến chuẩn cho cấu hình mới. `.env` và virtual environment được loại khỏi Git.

Review/Chat có cấu hình độc lập qua `OPENAI_REVIEW_REASONING_EFFORT`, `OPENAI_CHAT_REASONING_EFFORT`, `OPENAI_REVIEW_MAX_OUTPUT_TOKENS`, `OPENAI_CHAT_MAX_OUTPUT_TOKENS`. CLI `--reasoning-effort` và `--max-output-tokens` ưu tiên hơn môi trường. Khi dùng GPT-5.4/Mini, defaults là Review `high`/16.384 tokens, Chat `medium`/8.192 tokens; model legacy giữ 4.096 tokens và không gửi reasoning. Đây là defaults khởi điểm, không phải kết luận benchmark.

Temperature mặc định 0.0 chỉ gửi với GPT-4.1/GPT-4o Mini và GPT-5.4 effort `none`. Khi bật reasoning, bỏ `--temperature`; override tường minh kể cả 0 bị từ chối trước HTTP. GPT-5.4 Mini V1 bỏ temperature và từ chối custom temperature do chưa xác nhận riêng khả năng này. Effort hợp lệ cho GPT-5.4/Mini: `none`, `low`, `medium`, `high`, `xhigh`; model legacy từ chối cấu hình effort. CLI phân biệt temperature bỏ trống với giá trị 0. Không sửa `.env` tự động.

Không đưa API key vào source code hoặc output. CLI không in nội dung lỗi API gốc có thể chứa dữ liệu nhạy cảm. Mỗi lần chạy CLI thực hiện một request đếm input tokens và một request tạo review; OpenAI có thể tính phí cho inference và SDK có thể retry lỗi tạm thời.

## Chạy review

Sau khi activate virtual environment:

```bash
python3 scripts/review_academic_profile.py \
  --profile data/student_academic_profile.json \
  --jd data/sample_jd.txt \
  --output data/jd_academic_review.json
```

Có thể dùng `.venv/bin/python` thay `python3` nếu chưa activate. JD phải là file `.txt` UTF-8 không rỗng; không cần job title hoặc định dạng cố định. `--profile` và `--output` có default như ví dụ, còn `--jd` là bắt buộc.

Prompt ổn định nằm trong `scripts/academic_review_prompt.py`. Engine trong `scripts/academic_review.py` đọc profile nguyên vẹn, gửi tất cả môn/CLO và JD trong các message dữ liệu riêng, rồi gọi `client.responses.parse` với schema Pydantic. Không sử dụng tools, web search, skill extraction hoặc retrieval.

### Giới hạn context và lỗi

Preflight đếm instructions, toàn bộ input và schema bằng cùng model/reasoning với generation, rồi cộng output budget đã cấu hình (bao gồm reasoning tokens). Registry xác nhận alias/snapshot của GPT-4o Mini (128.000 context), GPT-4.1 (1.047.576), GPT-5.4 (1.050.000) và GPT-5.4 Mini (400.000). `--context-window` chỉ đặt trần nhỏ hơn hoặc bằng context đã xác nhận; model/snapshot chưa có capability bị từ chối dù cung cấp context override. Ví dụ tái lập baseline:

```bash
OPENAI_MODEL=gpt-4.1 .venv/bin/python scripts/review_academic_profile.py \
  --jd data/sample_jd.txt --context-window 1047576
```

Không đặt giới hạn lớn hơn thực tế. CLI không tự cắt profile/JD và generation dùng `truncation=disabled`. Timeout là 180 giây khi bật reasoning, 60 giây ở cấu hình khác; SDK retry tối đa hai lần cho lỗi tạm thời, nên toàn bộ lần chạy có thể lâu hơn 60 giây. Lỗi xác thực, quota, context, refusal, response chưa hoàn tất hoặc schema/evidence không hợp lệ đều trả exit code 1. Không tự tạo review thay thế hoặc sửa evidence khi có lỗi.

Mẫu live cuối được tạo bằng `gpt-4.1` với lệnh override trên, không sửa `.env`. Trong các ca đã kiểm tra, `gpt-4o-mini` bỏ sót bằng chứng quan trọng dù JSON hợp lệ; dùng `gpt-4.1` khi muốn tái lập cấu hình của mẫu cuối, đồng thời đọc các giới hạn semantic trong báo cáo. Context 1.047.576 và Structured Outputs của model này được xác nhận trong [tài liệu GPT-4.1](https://developers.openai.com/api/docs/models/gpt-4.1).

Output được ghi UTF-8 bằng thao tác thay thế file nguyên tử sau validation; lỗi generation không ghi đè output đã có. Output không được trùng profile/JD, kể cả symlink hoặc hardlink. Muốn lưu nhiều review, chọn các output path khác nhau.

## JSON đầu ra và bằng chứng

JSON có bốn field bắt buộc:

| Field | Nội dung |
| --- | --- |
| `review_type` | Luôn là `academic_knowledge_review`. |
| `overview` | Nhận xét tổng quan ngắn bằng tiếng Việt, tập trung vào JD. |
| `requirement_reviews` | Các yêu cầu kiến thức đáng kể, kèm `jd_requirement`, `coverage`, `comment`, `evidence`. |
| `conclusion` | Kết luận học thuật cân bằng, không đưa ra điểm tuyển dụng. |

Coverage dùng đúng ba giá trị: `covered` cho phạm vi kiến thức được CLO hoặc course description trực tiếp hỗ trợ; `related` cho nội dung có liên hệ đáng kể nhưng chưa xác nhận đầy đủ yêu cầu; `not_evidenced` khi không có CLO hoặc metadata đủ liên quan. Description chỉ xác nhận phạm vi chương trình; tools đơn thuần tối đa `related`, không xác nhận sinh viên sử dụng thành thạo. Không biến coverage thành đánh giá đạt/trượt tuyển dụng.

Evidence nhận một trong hai dạng: `{"course_code": "CPV301", "clo": "CLO8"}` hoặc `{"course_code": "ADY201m", "metadata_field": "tools"}`. `metadata_field` chỉ nhận `description`/`tools` có giá trị không rỗng trong đúng môn. Engine kiểm tra CLO thuộc đúng môn, reference trùng, field giả và object trộn hai dạng. `covered`/`related` cần evidence; `not_evidenced` có mảng rỗng. Tools-only evidence không được `covered`. Score/achievement phải dùng reference CLO, không được đưa giá trị vào evidence. Reference/session legacy vẫn load được.

Score, achievement và description có nguồn duy nhất là profile đầu vào. Loader chấp nhận score hữu hạn 0–10 hoặc `null` đi cùng `not_evaluated`; không tính lại hoặc phân loại lại achievement theo score. Mã môn/CLO trùng, field sai hoặc description rỗng khiến input bị từ chối.

Salary, location, working hours và thông tin hành chính không được đánh giá học thuật. JD chỉ có các thông tin này có thể trả `requirement_reviews: []` với lời giải thích phù hợp. Với kinh nghiệm nghề nghiệp, review chỉ nêu nền tảng học thuật liên quan và phần kinh nghiệm chưa được hồ sơ xác nhận.

## Kiểm thử

```bash
.venv/bin/python -m pytest -q
```

Các test mới mock SDK và chặn HTTP, không gửi profile tới OpenAI hoặc phát sinh phí. Test bao gồm loaders, schema, references, context, lỗi API, đường dẫn output, tính nguyên vẹn dữ liệu và cách tách JD chứa prompt injection khỏi instructions. Test mock prompt injection kiểm tra cách tạo request; khả năng model chống injection được kiểm tra riêng bằng live evaluation.

Các JD đánh giá bổ sung nằm trong `data/academic_review_evaluation/`: SQL/Data Analysis, Quantum Computing/FPGA và Computer Vision chứa prompt injection. Chạy chúng bằng cùng CLI với output path riêng nếu muốn đánh giá lại bằng API thật. Review mẫu và đánh giá thủ công được mô tả trong [báo cáo đánh giá](docs/academic_review_evaluation.md), có phân biệt output ban đầu chưa đạt và output cuối đã kiểm tra.

## Academic Chat

Chat giải thích profile, JD hiện tại và Initial Review đã có. Profile là nguồn sự thật cho descriptions, scores và achievement. Review là phân tích trước đó: chat có thể sửa diễn giải của review bằng CLO phù hợp, nhưng không ghi lại review hoặc profile. Không chạy lại Review Engine khi đặt câu hỏi.

```bash
.venv/bin/python scripts/chat_academic_profile.py \
  --profile data/student_academic_profile.json \
  --jd data/sample_jd.txt \
  --review data/jd_academic_review.json
```

CLI dùng cùng `.env` nhưng chọn biến stage Chat riêng trước biến model chung. Với `MODEL=gpt-4.1` hiện có, không cần `--context-window`. Lời chào hiển thị overview từ review bằng code; không phát sinh generation. Mỗi câu hỏi thực hiện một preflight và một generation, rồi chỉ hiển thị `reply` tiếng Việt sau validation. Không dùng thêm LLM để render.

Có thể hỏi “Vì sao YOLO chưa có bằng chứng?”, “CLO đó bao nhiêu điểm?”, “Môn nào hỗ trợ JD?” hoặc so sánh CLO giữa các môn. Câu hỏi về SQL trong profile vẫn hợp lệ khi JD đang xét là Computer Vision, nhưng chat không biến SQL thành yêu cầu mới của JD. Yêu cầu tutorial, code, bài tập, roadmap, Coursera, CV và dự đoán tuyển dụng nằm ngoài phạm vi; chat trả lời phần học thuật của câu hỏi hỗn hợp và từ chối phần còn lại. Đây là policy trong prompt, không phải bộ phân loại hoặc bảo đảm ngữ nghĩa tự động.

“Mình cần bổ sung những kiến thức gì?” được hiểu là đối chiếu các mảng kiến thức JD yêu cầu với bằng chứng học thuật hiện có. Chat được hướng dẫn trả lời trực tiếp, tách yêu cầu kinh nghiệm nghề nghiệp và không suy từ nội dung chưa được xác nhận thành kiến thức sinh viên thực sự thiếu. Nhãn `basic`/`good`/`excellent` thuộc từng CLO, không phải mức năng lực tổng thể. Độ dài và cách trình bày thích ứng với câu hỏi; có thể yêu cầu “nói ngắn gọn hơn” hoặc “tóm tắt cuộc trao đổi”, không có khuôn cố định về số từ, đoạn hay bullet.

Chat có thể nêu chủ đề JD đáng kiểm tra hoặc cân nhắc bổ sung **nếu bạn chưa học ngoài trường**. Đây là gợi ý chủ đề có điều kiện, không phải kết luận bạn thiếu năng lực; tutorial, code, khóa học và roadmap vẫn ngoài phạm vi. History chỉ giúp hiểu cuộc trao đổi; các claim trong summary phải đối chiếu lại description và không giữ nhận xét trước sai chỉ vì nó đã xuất hiện.

Nhập `exit` hoặc `quit` để kết thúc; EOF và Ctrl+C được xử lý an toàn. Các lỗi startup trả exit code 1; lỗi trong lượt chat được thông báo và cho phép thử lại. Các câu hỏi thất bại không xuất hiện trong history.

### Lưu và mở lại phiên

Mặc định history chỉ ở trong bộ nhớ và mất khi đóng CLI. Thêm `--persist` để lưu JSON vào `data/chat_sessions/`:

```bash
.venv/bin/python scripts/chat_academic_profile.py \
  --jd data/sample_jd.txt --persist
```

CLI in Session ID dạng UUID 32 ký tự hex. Thay `SESSION_ID` dưới đây bằng ID đó để resume với cùng ba nguồn:

```bash
.venv/bin/python scripts/chat_academic_profile.py \
  --jd data/sample_jd.txt --resume SESSION_ID
```

`--session-dir` chọn thư mục khác; cần dùng lại cùng thư mục khi resume. `--persist` và `--resume` loại trừ nhau. Thư mục mặc định được loại khỏi Git; lịch sử tại thư mục tùy chỉnh do bạn quản lý.

Session lưu version, UUID, paths và SHA-256 của profile/JD/review, cùng các cặp message user–assistant và evidence. Không lưu settings hoặc API key. History assistant giữ references để giải nghĩa follow-up; nội dung user và assistant trước đó không trở thành nguồn học thuật mới.

Paths/fingerprints được kiểm tra khi resume và trước mỗi lượt. Một trong ba nguồn thay đổi khiến phiên bị từ chối; tạo phiên mới với các nguồn mới. File history hỏng, evidence giả, roles sai hoặc lượt dở dang không được tự sửa. Một phiên chỉ được một tiến trình mở cùng lúc nhờ khóa file POSIX. Khóa được nhả khi đóng hoặc tiến trình kết thúc, dù file `.lock` vẫn còn.

Cặp hỏi–đáp chỉ được commit sau validation và ghi file nguyên tử thành công. API/evidence/save failure không làm thay đổi history trước đó. Ctrl+C kết thúc phiên; nếu interruption xảy ra quanh thời điểm commit, resume đọc trạng thái JSON đầy đủ đã lưu, không tiếp tục bằng trạng thái bộ nhớ cũ.

Persistence V1 yêu cầu POSIX; session trong bộ nhớ không cần khóa file. Đây là prototype local dùng quyền filesystem hiện có, không có authentication hoặc bảo đảm cách ly người dùng như một dịch vụ production.

### Giới hạn hội thoại và debug

Defaults là 20 lượt sinh viên thành công, tối đa 4.000 ký tự mỗi câu hỏi; output budget theo Chat settings (8.192 cho reasoning model, 4.096 cho legacy). Các reply từ chối ngoài phạm vi vẫn tính là lượt thành công; lỗi không tính lượt. Dùng `--max-turns`, `--max-message-chars`, `--context-budget` để đổi giới hạn. Context budget bao gồm input và dự phòng output, phải lớn hơn output budget và không vượt context model.

Luôn gửi đủ profile, JD, review và history đã commit. Không cắt history hoặc dùng LLM tóm tắt. Khi vượt budget hoặc giới hạn lượt, bắt đầu phiên mới; khi resume với limit nhỏ hơn history hiện có, CLI báo lỗi. `--debug` chỉ log Session ID, số lượt và model, không log payload hoặc credential.

### Dùng engine từ Python

Không cần terminal I/O để dùng engine:

```python
from scripts.academic_chat import AcademicChatSession

with AcademicChatSession.from_files(
    "data/student_academic_profile.json",
    "data/sample_jd.txt",
    "data/jd_academic_review.json",
) as session:
    result = session.send("CLO về Object Detection có điểm bao nhiêu?")
    print(result.reply)
```

`send()` trả `AcademicChatResponse` có đúng `reply` và `evidence`. Caller có thể inject `settings` và SDK `client`; client được inject vẫn thuộc caller. Dùng context manager hoặc `.close()` để nhả khóa phiên. History được trả dưới dạng bản copy.

Tests chat mock SDK và chặn HTTP giống review; không phát sinh phí. Transcript thật, kết quả resume và các vấn đề semantic được ghi trong [báo cáo Academic Chat](docs/academic_chat_evaluation.md).

## Giới hạn của review và chat

Validator xác minh cấu trúc JSON và danh tính CLO, không chứng minh mọi diễn giải ngữ nghĩa là đúng. Model vẫn có thể bỏ sót requirement, chọn CLO hợp lệ nhưng không liên quan, hoặc suy diễn quá mức; cần đối chiếu descriptions và achievement khi sử dụng kết quả. Các vòng live sau cập nhật style cho thấy follow-up và rút gọn tốt hơn, nhưng vẫn có lỗi gộp kinh nghiệm vào kiến thức, thiếu CLO cho từng ý và suy từ `basic` sang phạm vi kiến thức. Báo cáo ghi rõ các lượt chưa đạt; một lần generation đạt không bảo đảm mọi lần hoặc mọi JD đều đạt.

V1 không tạo skill taxonomy, gợi ý khóa học/kế hoạch đào tạo, roadmap, CV, embeddings, overall match percentage hoặc readiness score. Scoring Engine, dữ liệu học thuật gốc và các prompt cũ không được component này sửa hoặc dùng để tính lại điểm.

## Benchmark JD thực tế

Benchmark gồm 15 fixtures tại `data/academic_benchmark/`: JD00 sao chép nguyên mẫu nội bộ, JD01–JD14 viết lại từ posting đã kiểm tra. Manifest ghi nguồn và hash; bảy posting ATS dùng text từ chỉ mục tìm kiếm, không bảo đảm vacancy còn mở. Rubric/expected behaviors là dữ liệu đánh giá thủ công, không gửi tới model.

Kiểm tra offline không gọi API:

```bash
.venv/bin/python scripts/evaluate_academic_benchmark.py
.venv/bin/python -m pytest -q
```

Live phải bật `--live`; chọn `--phase pilot`, `benchmark`, `deep` hoặc `temperature`, dùng cùng `--run-id` để tiếp tục kết quả hợp lệ. `--case` có thể lặp để chọn JD. Ví dụ dưới đây mở một run mới có phí:

```bash
.venv/bin/python scripts/evaluate_academic_benchmark.py \
  --live --phase benchmark --case JD05 --run-id my-evaluation --max-generations 80
```

Runner đếm tối đa 80 HTTP generation trong một run, gồm dispatch thất bại và SDK retries; preflight được ghi riêng. Budget không reset khi resume. Run lock POSIX chặn hai tiến trình cùng mở; thay nguồn/prompt/schema/model/budget khiến resume bị từ chối. Case lỗi giữ raw output và không tự retry hoặc dùng review thay thế. Khi API/quota/budget lỗi, phase dừng. Run ID mới có ngân sách riêng: phải giữ cùng ID để quản lý trần của một đợt đánh giá. Benchmark dùng persistence hiện có trong thư mục artifacts; mặc định CLI Chat vẫn memory-only.

Đợt `internship-20261013` đã hoàn tất **78 generation + 78 preflight**, model `gpt-4.1-2025-04-14`, không retry; **238 tests pass**. Mỗi JD có review mới và ít nhất ba lượt chat; bốn phiên có hai lượt sâu; sáu candidate 0.3 replay cùng request context của baseline 0.0. Đã đọc thủ công cả 78 output và giữ reply/evidence nguyên bản. **Còn 30 output có P0**, nên cần sửa grounding trước nghiệm thu dù tất cả schema/references hợp lệ. Kết quả từng JD, tám regressions, toàn bộ findings và reply A/B nằm trong [báo cáo benchmark](docs/academic_benchmark_evaluation.md).

## Tài liệu API

- [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses)
- [OpenAI Python SDK và timeout/retry](https://developers.openai.com/api/reference/python)
- [Responses input token count](https://developers.openai.com/api/reference/python/resources/responses/subresources/input_tokens/methods/count)
- [GPT-4o Mini và giới hạn context](https://developers.openai.com/api/docs/models/gpt-4o-mini)
- [GPT-4.1 và giới hạn context](https://developers.openai.com/api/docs/models/gpt-4.1)


## Profile enriched và comparison 12 lượt

Builder giữ nguyên scoring/CLO, bổ sung raw metadata tại cấp môn từ folder đã chọn. Metadata thiếu/hỏng/sai subject_code không làm mất môn/CLO: phần metadata bị bỏ, CLI cảnh báo và validation report ghi lỗi. `tools=""` được giữ nguyên; textbook/Internet và các lựa chọn công cụ không trở thành bằng chứng đã sử dụng. Loader đọc cả profile legacy và enriched.

```bash
.venv/bin/python scripts/build_student_academic_profile.py \
  --output data/student_academic_profile.enriched.json \
  --report-output data/clo_scoring_report.enriched.json
.venv/bin/python scripts/review_academic_profile.py \
  --profile data/student_academic_profile.enriched.json \
  --jd data/sample_jd.txt --output data/jd_academic_review.enriched.json \
  --model gpt-5.4 --reasoning-effort high --max-output-tokens 16384
.venv/bin/python scripts/chat_academic_profile.py \
  --profile data/student_academic_profile.enriched.json \
  --jd data/sample_jd.txt --review data/jd_academic_review.enriched.json \
  --model gpt-5.4-mini --reasoning-effort medium --max-output-tokens 8192
```

Dùng file output mới để giữ profile/manifest/review lịch sử. Defaults đường dẫn CLI cũ vẫn giữ tương thích; khi dùng enriched, truyền `--profile` như trên. Session luôn khóa fingerprint nguồn ban đầu; thay profile/JD/review yêu cầu tạo session mới.

```bash
# Chuẩn bị và kiểm tra ma trận; không gọi API.
.venv/bin/python scripts/evaluate_academic_benchmark.py --phase comparison
# Có phí: chỉ dùng khi ngân sách đợt này đã được duyệt.
.venv/bin/python scripts/evaluate_academic_benchmark.py --phase comparison --live \
  --run-id metadata-models-20261013 --max-generations 12 --max-cost-usd 2.5
```

Comparison cố định 8 Review (JD01/JD05: legacy GPT-4.1, enriched GPT-4.1, Mini high, GPT-5.4 high) và 4 Chat JD11 (GPT-4.1, Mini low/medium, GPT-5.4 medium). Chat dùng cùng Review/history trước lượt 5 và cùng probe mới; không phải so sánh end-to-end pipeline. Output ceilings: Review 16.384, Chat 8.192. Một ledger chặn tối đa 12 generation HTTP, 12 preflight và 2,50 USD dựa trên reservation input không cache/output ceiling; SDK retry tắt trong comparison. Input vượt 32.000 tokens bị từ chối, không cắt context. Giữ cùng run ID khi resume; mọi condition đã thử, kể cả thất bại, không được sinh lại.

Raw traces lưu usage/cache/reasoning, snapshot, temperature thực gửi, latency, schema/evidence validation và incomplete reason. Semantic P0/P1/P2 được đọc thủ công; valid JSON không chứng minh grounding đúng. Giá standard được kiểm tra ngày 13/10/2026; cost là ước tính, không phải hóa đơn. Model registry/giá cần được kiểm tra trước các đợt mới. Mẫu 12 lượt chỉ hỗ trợ khuyến nghị sơ bộ; defaults và CLI vẫn có thể điều chỉnh. Xem [báo cáo metadata/model](docs/academic_metadata_models_evaluation.md).

## Benchmark reasoning trên 5 JD

Run `reasoning-five-jds-20261013` dùng manifest riêng với profile enriched, JD01/JD05/JD07/JD10/JD11 và bốn câu hỏi nguyên văn cho mỗi JD. Mỗi session bắt đầu từ Review mới của đúng JD. Cấu hình và prompts/schema được đóng băng; không gửi temperature, không cắt context và không sinh lại request đã attempted.

```bash
# Offline: lập kế hoạch, xác minh nguồn/cấu hình; không gọi OpenAI.
.venv/bin/python scripts/evaluate_academic_benchmark.py \
  --manifest data/academic_benchmark/evaluations/reasoning-five-jds-20261013/manifest.json \
  --run-id reasoning-five-jds-20261013 \
  --plan-output data/academic_benchmark/evaluations/reasoning-five-jds-20261013/plan.json \
  --max-generations 25 --max-preflights 25 --max-cost-usd 6 --max-retries 0 \
  --continue-on-case-error \
  --review-model gpt-5.4 --review-reasoning-effort high \
  --review-max-output-tokens 32768 --review-timeout 360 \
  --chat-model gpt-5.4-mini --chat-reasoning-effort medium \
  --chat-max-output-tokens 8192 --chat-timeout 180
```

Thêm `--live` để thực hiện run đã được duyệt. Giữ nguyên run ID, manifest và options khi resume: ledger không reset, trace thành công có thể khôi phục offline, attempt không chắc chắn được bỏ qua. Review lỗi sẽ bỏ Chat của JD đó; Chat lỗi dừng các câu tiếp theo trong JD, giữ history thành công và chuyển JD khác. Hết budget hoặc lỗi xác thực/kết nối toàn cục dừng run. Timeout chưa có usage giữ reservation; reasoning được tính trong output tokens. Timeout mặc định của ứng dụng và giới hạn comparison 12 lượt vẫn giữ nguyên.

Kết quả run: 25 generation + 25 preflight, 25/25 hoàn tất; cost theo usage khoảng 1,257352 USD. Review không có P0 quan sát trong năm ca; ba reply Chat có P0 attribution dù reference validation passed. Xem [báo cáo 5-JD reasoning](docs/academic_reasoning_five_jds_evaluation.md) trước khi dùng kết quả làm căn cứ triển khai.
