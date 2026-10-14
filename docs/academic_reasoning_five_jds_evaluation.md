# SkillBridge V1 — Benchmark reasoning trên 5 JD

Run **`reasoning-five-jds-20261013`**, ngày 13/10/2026, Asia/Bangkok, đã hoàn tất đúng **5 Initial Review + 20 lượt Academic Chat**, với **25 generation + 25 preflight**, không retry hoặc generation phụ. Tất cả 25 output hoàn tất và vượt schema/evidence validation. **Đánh giá semantic chưa đạt cho toàn pipeline: 3/20 reply Chat có P0, thuộc JD05, JD10 và JD11.** Không ghi nhận P0 trong năm Review; một Review còn P1 về phạm vi coverage.

Chi phí standard ước tính từ usage là **1,25735240 USD**, không có request thiếu usage. Đây là chi phí tính theo giá công bố và token API trả về, không phải hóa đơn. Các kết quả dưới đây giữ nguyên model outputs, không sửa rồi chấm lại, không dùng API judge.

## A. Engineering và tính toàn vẹn

### Cấu hình thực tế

| Stage | Requested model | Snapshot trả về | Effort | Output ceiling | Timeout |
|---|---|---|---|---:|---:|
| Initial Review | gpt-5.4 | gpt-5.4-2026-03-05 | high | 32.768 | 360 giây |
| Academic Chat | gpt-5.4-mini | gpt-5.4-mini-2026-03-17 | medium | 8.192 | 180 giây |

Chỉ dùng JD01, JD05, JD07, JD10, JD11 và `student_academic_profile.enriched.json`. Profile vẫn **15 môn, 122 CLO, 15/15 metadata hợp lệ**, giữ bốn `tools=""` và toàn bộ scores/achievements. Hash profile: `b0bfa72fdc04f8d2cfc94e68fd7b4745387cd378a923f55eb94e2aef391bf531`.

Mỗi JD có một Review mới và một session riêng; bốn câu hỏi nguyên văn từ yêu cầu được replay liên tiếp với full history của chính JD đó. Không dùng Review/history cũ hoặc của JD khác. Preflight/generation giữ cùng input, instructions, model, reasoning và schema; generation không gửi temperature, giữ `store=False`, `truncation=disabled` và Pydantic parsing. Không thêm công cụ hoặc tham số model chưa được xác nhận.

### Thay đổi nhỏ trong runner

| File | Thay đổi |
|---|---|
| `scripts/academic_review.py` | Settings thêm `request_timeout` hữu hạn dương; defaults 180/60 giây giữ nguyên. Cả count và parse nhận timeout theo settings, kể cả injected client. Loader có API-key override cho offline plan, không cần credential thật. |
| `scripts/evaluate_academic_benchmark.py` | Thêm manifest riêng, stage timeout flags, preflight/cost caps, retry option, tiếp tục case sau lỗi và offline plan. Ledger persist trước HTTP; resume khôi phục output hợp lệ offline, không dispatch lại attempt không chắc chắn. Recording/metrics dùng đúng stage. |
| `scripts/academic_model_comparison.py` | Tách helper metrics để runner dùng chung; tái sử dụng cost estimator và tính phụ phí GPT-5.4 khi input vượt 272.000. Comparison cũ vẫn giữ 12 generation/12 preflight/2,50 USD và input cap 32.000. |
| `tests/test_five_jd_benchmark.py` | 17 test cases mock về dispatch, budgets, history, timeout, lỗi và crash/resume; chặn HTTP thật. |
| `README.md` | Hướng dẫn offline/live/resume cùng flags cụ thể cho benchmark này. |

Không sửa scoring, production prompts, schemas, JD fixtures, profile snapshots, metadata gốc, `.env` hoặc historical annotations. Báo cáo này và toàn bộ artifacts của run mới là phần bàn giao bổ sung.

**Checks:** baseline 283 tests; trước live, suite sau mở rộng đạt **298 passed**, `pip check` sạch. Hai kiểm tra biên bổ sung cho input 80.000 và phụ phí long context đưa suite cuối lên **300 passed**; chúng không thay production code hoặc cấu hình inference. `pip check` cuối vẫn không có dependency hỏng. Không thêm dependency.

Tests kiểm tra timeout thực ở HTTP transport là Review 360/Chat 180, đúng model/effort/output, temperature omitted, bốn lượt history, profile/JD/Review pairing, SDK retry=0, cap vật lý 25/25, cost reservation xuyên resume, crash sau Review và trước Chat commit, unknown attempt không regenerated, lỗi Chat giữ history và auth failure dừng run. Offline plan không tạo SDK hoặc tiêu thụ preflight.

[Offline verification](../data/academic_benchmark/evaluations/reasoning-five-jds-20261013/offline_verification.json), [plan đã đóng băng](../data/academic_benchmark/evaluations/reasoning-five-jds-20261013/plan.json) và [manifest riêng](../data/academic_benchmark/evaluations/reasoning-five-jds-20261013/manifest.json) giữ cấu hình, nguồn, câu hỏi, hashes và ceilings. [Pairing validation](../data/academic_benchmark/evaluations/reasoning-five-jds-20261013/pairing_validation.json) xác nhận full profile, đúng JD/Review, history và parity của count/generation cho mọi operation.

**Integrity: 885 file được bảo vệ không đổi**, gồm dữ liệu học thuật, course metadata, JD/manifest/history/artifacts lịch sử, báo cáo cũ, `.env`, prompt files và model registry. Fingerprints Review/Chat schemas giữ nguyên. [Integrity check](../data/academic_benchmark/evaluations/reasoning-five-jds-20261013/integrity_check.json) đối chiếu với snapshot trước thay đổi; [ledger](../data/academic_benchmark/evaluations/reasoning-five-jds-20261013/run.json) lưu từng physical dispatch. Live bắt đầu 21:34:31 và kết thúc 21:52:03, khoảng 17 phút 32 giây; không resume hoặc retry live.

## B. Initial Review: completion và chất lượng học thuật

Các token output dưới đây **đã bao gồm reasoning**. Latency là toàn operation, gồm preflight, generation và ghi/validation local.

| JD | Completion / validation | Giây | Input | Cached input | Output | Reasoning | Cost USD | P0/P1/P2 |
|---|---|---:|---:|---:|---:|---:|---:|---|
| JD01 | completed / passed | 135,749 | 16.049 | 15.104 | 10.468 | 8.383 | 0,163159 | 0/0/0 |
| JD05 | completed / passed | 119,863 | 16.080 | 15.104 | 10.323 | 8.286 | 0,161061 | 0/0/0 |
| JD07 | completed / passed | 184,314 | 16.068 | 15.104 | 13.715 | 11.285 | 0,211911 | 0/0/0 |
| JD10 | completed / passed | 173,407 | 16.084 | 15.104 | 14.311 | 11.912 | 0,220891 | 0/0/0 |
| JD11 | completed / passed | 146,697 | 16.079 | 15.104 | 11.445 | 9.440 | 0,177889 | 0/1/0 |

Các counts là số findings thủ công, không phải validator errors. Parsed Reviews nguyên bản được giữ ở [reviews](../data/academic_benchmark/evaluations/reasoning-five-jds-20261013/reviews); raw responses/input/schema nằm trong [requests](../data/academic_benchmark/evaluations/reasoning-five-jds-20261013/requests).

- **JD01 — CV:** đúng CPV301 image processing/object detection, AIG202c/CLO2 cho ML/DL/Neural Networks ở mức khái niệm. Không suy scikit-learn, TensorFlow, Keras, PyTorch hoặc dự án nghề nghiệp. AIL303m/CLO10 basic và DBI202 basic được giữ riêng. Course descriptions hỗ trợ phạm vi curriculum; English/thời lượng internship vẫn chưa xác nhận. Không ghi nhận P0/P1/P2.
- **JD05 — Data Analyst:** giữ Python **OR** R; nhánh Python có bằng chứng, ADY201m/CLO3 nhắc R nhưng `use at least one` không xác định công cụ được chọn. SQL và BI giữ **preferred**. Đúng MAS291 hypothesis testing, MAI391 regression/PCA/SVM và optimization. SQL có DBI202 basic, ADY201m good/excellent; không tạo mức SQL chung. Dashboard dẫn DAP391m description/CLO4/CLO7, không suy Power BI/Tableau/Google Data Studio. Không ghi nhận P0/P1/P2.
- **JD07 — Data Analyst:** đúng cleaning/wrangling, chart/dashboard và SQL foundations. Excel/Maxima ở metadata được giữ là ví dụ/lựa chọn công cụ, chưa phải outcome được chấm riêng. Không suy GPA ≥7.5 hoặc English B1 từ các điểm CLO. AIL303m/CLO10 basic được nêu cân bằng. Không ghi nhận P0/P1/P2.
- **JD10 — GenAI:** prompting ở AIG202c/CLO4 không thành prompt testing/structured outputs; Python libraries không thành pandas/numpy/JSON/CSV. Giữ Git/GitHub là curriculum/tools, chưa xác nhận direct Git operations. RAG/MCP/agent frameworks và BigQuery/Snowflake không được xác nhận đích danh. Responsibilities và preferred prior experience được giữ riêng. Không ghi nhận P0/P1/P2.
- **JD11 — Backend:** đúng API ở ADY201m/CLO5, DAP391m/CLO5–6; SQL Server là RDBMS tương tự trong yêu cầu PostgreSQL/MySQL **OR similar**, không phải bằng chứng đã dùng PostgreSQL. SQL/basic được giữ. **P1:** row “integrate AI and enterprise services” gộp AND rồi đặt `covered`, trong khi references trực tiếp chỉ xác nhận Watson/AI services. Cần tách phần có nguồn hoặc giữ `related` với giới hạn enterprise-specific; đây không phải lỗi điểm hoặc bịa framework.

Năm Review không có P0 được quan sát, nhưng đây là năm output cụ thể. Một coverage boundary chưa chuẩn và mẫu nhỏ khiến kết quả chưa đủ chứng minh Review luôn đúng.

## C. Academic Chat: bốn lượt mỗi JD

Tất cả **20/20 lượt** hoàn tất, schema/reference passed và được commit vào năm session độc lập. Không có lượt `not_attempted`, không dùng failed output làm history. [Conversations](../data/academic_benchmark/evaluations/reasoning-five-jds-20261013/conversations) và [sessions](../data/academic_benchmark/evaluations/reasoning-five-jds-20261013/sessions) giữ toàn bộ user/assistant history cùng source fingerprints.

### Kết quả từng JD

| JD | Lượt hoàn tất | Tổng cost Chat USD | Continuity và grounding | Findings |
|---|---:|---:|---|---|
| JD01 | 4/4 | 0,075923 | Đúng CLO8 Object Detection, CLO9 Face Recognition/Tracking; giữ Understand/Implement và Explain, đúng 8.81/excellent. Summary không nâng learning verb hoặc suy framework. | Không P0/P1; P2 ở lượt 1,2,4 do lặp nhiều trích English. |
| JD05 | 4/4 | 0,067937 | SQL/R/tools và band từng CLO được giải thích đúng ở lượt 3. Lượt 2 gán sai confidence intervals; lượt 4 dùng CLO7 đúng nhưng không đính chính lỗi cũ tường minh. | P0 lượt 2; P1 về trích dẫn/thiếu reference, advice calibration và diễn giải basic; P2 lượt 1. |
| JD07 | 4/4 | 0,070592 | Không suy GPA/English; SQL và cleaning bands đúng. Lượt 3 bỏ DAP391m/CLO1=8.45/good, lượt 4 đưa lại đúng. | P1 lượt 3 về thiếu evidence quan trọng; P2 lượt 4 về lặp/summary offer. |
| JD10 | 4/4 | 0,045276 | Lượt 1–3 không suy RAG/MCP/pandas/numpy; prompting khác công nghệ chuyên biệt. Summary lượt 4 tự thêm attribution sai MAS291/CLO9. | P0 lượt 4; P1 lượt 1 về completed project wording; P2 lượt 4 thêm CV ít liên quan. |
| JD11 | 4/4 | 0,062715 | API đúng ADY201m/CLO5, DAP391m/CLO5–6, AIL303m/CLO1; không gán API cho CLO7 hoặc suy backend frameworks. Lượt 1 sai CSI106/CLO4; summary dùng network đúng nhưng không đính chính tường minh. | P0 lượt 1 về attribution hệ thống; P2 lượt 4 về lặp. |

**Ba lỗi P0, với nguồn đối chiếu:**

1. [Chat JD05 lượt 2](../data/academic_benchmark/evaluations/reasoning-five-jds-20261013/requests/chat-JD05-2.json) gán **MAS291/CLO9** cho “Construct and interpret confidence intervals...”. Canonical **CLO7** mới là confidence intervals; **CLO9** là simple linear regression. Reference ID tồn tại nhưng description không hỗ trợ claim.
2. [Chat JD10 lượt 4](../data/academic_benchmark/evaluations/reasoning-five-jds-20261013/requests/chat-JD10-4.json) gán **MAS291/CLO9** cho “Construct and interpret confidence intervals... and simple linear regression...”. Gộp hai outcomes rồi dẫn một CLO không hợp lệ về nghĩa. Hai CLO cùng 9.43/excellent không làm attribution đúng. Claim này không nằm trong Review hoặc history trước lượt 4, và không được đưa từ session JD05.
3. [Chat JD11 lượt 1](../data/academic_benchmark/evaluations/reasoning-five-jds-20261013/requests/chat-JD11-1.json) gán **CSI106/CLO4** cho “Describe how different data type is stored inside a computer...”. Canonical **CLO3** nói data types/bit patterns; **CLO4** nói network layers. IDs hợp lệ không đủ kiểm tra nội dung.

**Các P1 đáng chú ý:** JD05 lượt 2 trộn wording của DAP391m/CLO7 vào câu trích ADY201m/CLO7 và không dẫn DAP391m/CLO7 dù nhắc nó; câu “không cần bổ sung gấp” vượt khả năng profile xác định nhu cầu cá nhân. JD05 lượt 4 gọi clustering/dimensionality reduction “ở mức cơ bản trong học phần này”, dễ biến achievement basic thành độ sâu syllabus. JD07 lượt 3 thiếu outcome trực tiếp Data Analysis DAP391m/CLO1. JD10 lượt 1 nói “bạn đã làm workflow dự án ... end-to-end” từ intended capstone outcome, trong khi profile không có artifact dự án cá nhân xác nhận hoàn tất; bối cảnh vẫn học thuật nên ghi P1, không P0 về employment.

**Correction và history:** summary JD05 dùng confidence intervals ở CLO7 đúng; summary JD11 dùng CSI106/CLO4 đúng cho network. Chúng không lặp attribution sai tương ứng, nhưng cũng không nói rõ câu trước đã sai. JD10 lại tạo lỗi mới trong summary. Không có Review P0 trong run này để trực tiếp đo khả năng Mini sửa một Review sai nghiêm trọng; bài API ở JD11 chứng minh giải thích đúng khi Review đã đúng, không phải thí nghiệm repair có seed sai.

**Completeness/naturalness:** câu hỏi rộng có thể cần nhiều nhóm bằng chứng; câu hỏi hẹp JD01 lượt 3 được trả lời đúng phạm vi. Không áp word limit, số bullet cố định hoặc thưởng cho độ ngắn. P2 được ghi vì trích English/lặp kết luận hoặc nội dung phụ ít liên quan, không vì reply dài. Một số summary đề nghị “tóm tắt tiếp” sau khi vừa tóm tắt, làm hội thoại mang tính mẫu. Nhìn chung API/framework boundaries tốt hơn, nhưng exact attribution và summary grounding vẫn là giới hạn quan trọng.

[Manual assessments đầy đủ](../data/academic_benchmark/evaluations/reasoning-five-jds-20261013/manual_assessments.json) có record cho **mọi output**, hash response, chín chiều rubric, notes và từng finding với claim gốc, nguồn canonical, severity và giải thích. Không sửa outputs trước grading. Các chiều là đánh giá định tính, không phải điểm match/tuyển dụng hoặc kiểm định thống kê.

## D. So sánh và giới hạn nghiệm thu

| JD | Initial Review P0 | Chat P0 | Completion | Main finding |
|---|---:|---:|---|---|
| JD01 | 0 | 0 | Review + 4/4 Chat | CV attribution/verbs và named-framework boundaries đúng; trình bày lặp. |
| JD05 | 0 | 1 | Review + 4/4 Chat | MAS291/CLO9 bị gán confidence intervals ở lượt 2. |
| JD07 | 0 | 0 | Review + 4/4 Chat | Không đổi 8.45/good thành excellent; lượt 3 bỏ outcome này, lượt 4 nêu đúng. |
| JD10 | 0 | 1 | Review + 4/4 Chat | Named technologies được giữ chưa xác nhận; summary tự thêm confidence-interval attribution sai. |
| JD11 | 0 | 1 | Review + 4/4 Chat | SQL/API đúng; CSI106/CLO4 bị gán description CLO3. Review còn P1 cho compound enterprise scope. |

Phân biệt kết quả:

- **Technical completion:** 25/25, timeout/incomplete/refusal/API failure đều 0.
- **Schema/evidence-ID validation:** 25/25 passed; không chứng minh description hỗ trợ từng claim.
- **Semantic:** 0/5 Review có P0; 1/5 có P1. Chat có **3/20 output chứa P0 (15%)**, thuộc **3/5 case (60%)**; 4 output có P1. Case có P0 không đạt semantic theo rubric hiện tại.
- **Presentation:** 7 reply Chat có P2; đây là vấn đề khác với lỗi dữ kiện hoặc completion. Không có P2 ở Review.

### Đối chiếu lịch sử cùng năm JD

Nguồn: [benchmark internship trước](academic_benchmark_evaluation.md) và [metadata/model comparison](academic_metadata_models_evaluation.md). Đối chiếu annotations nguyên bản; không sửa lịch sử hoặc gọi lại model.

| Phần so sánh cùng JD | Lịch sử GPT-4.1 | Run hiện tại | Diễn giải |
|---|---:|---:|---|
| 5 Review có P0 | 5/5 | 0/5 | Quan sát thấy các lỗi score/band, named libraries và SQL/API/CV attribution trước đây không tái xuất hiện trong năm Review mới. |
| Chat có P0, chỉ lấy lượt 1–3 của cả hai run | 7/15 | 2/15 | Những patterns CV/R/pandas-numpy/API cũ giảm; lỗi mới là MAS291/CLO9 và CSI106/CLO4. |
| Toàn bộ Chat mới, gồm lượt 4 | Không có cùng ma trận cố định | 3/20 | Thêm lỗi MAS291/CLO9 ở summary JD10; không lấy 15 replies lịch sử làm đối chứng cho 20 replies mới. |

Các tests lịch sử khác model, profile version, prompts, output budgets, câu hỏi và Review/history đầu vào. Vì vậy đây là **khác biệt quan sát**, không phải causal model improvement hoặc A/B có kiểm soát. Riêng comparison metadata trước cũng chỉ có một Chat probe JD11 với frozen Review/history; không thay thế end-to-end pipeline năm JD hiện tại.

Metadata hiện hữu ích để nhận Excel là curriculum example, RStudio/Git là tools context, SQL Server là named DBMS và dashboard là course description. Giới hạn `for example`/`use at least one` được giữ. Run này chỉ dùng enriched profile nên **không tách được tác động metadata** khỏi model hoặc prompts. MCP không bị gọi sai Multi-Channel Platform, nhưng replies không mở rộng tên đầy đủ nên không đủ đánh giá sâu cách hiểu Model Context Protocol. Không có intentional contaminated-history seed mới để kiểm định repair toàn diện.

## E. Usage, chi phí và latency

| Stage | Generation | Preflight | Input | Cached input | Output gồm reasoning | Reasoning | Total tokens | Cost USD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Review | 5 | 5 | 80.360 | 75.520 | 60.262 | 49.306 | 140.622 | 0,93491000 |
| Chat | 20 | 20 | 432.982 | 383.232 | 56.975 | 36.721 | 489.957 | 0,32244240 |
| Tổng | **25** | **25** | **513.342** | **458.752** | **117.237** | **86.027** | **630.579** | **1,25735240** |

Không cộng cached input thêm lần nữa vào input; không cộng reasoning thêm lần nữa vào output/cost. Token-count preflight không được coi là generation usage. Tất cả 25 generation có usage; unknown-usage reservation cuối **0 USD**.

Giá standard /1M input/cached/output được kiểm tra trước live: GPT-5.4 **2,50/0,25/15,00 USD**, Mini **0,75/0,075/4,50 USD**. Với GPT-5.4 input >272.000, estimator tính hệ số input 2× và output 1,5×; request hiện tại đều dưới ngưỡng. Nguồn: [GPT-5.4](https://developers.openai.com/api/docs/models/gpt-5.4), [GPT-5.4 Mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini).

Trần lập kế hoạch **4,794880 USD** giả định 32.000 uncached input mỗi Review, 80.000 mỗi Chat và dùng hết output ceiling; chúng không phải context truncation caps. Preflight thực tế là khoảng 16.000 input cho Review và 19.900–23.200 cho Chat. Tổng reservations khi dispatch là **3,72051650 USD**, còn cost từ usage thực tế là **1,25735240 USD**, đều dưới trần **6,00 USD**. Run dừng ở đúng ma trận; không dùng phần tiền còn lại cho thử nghiệm.

Cached input khá cao trong run này. Không dùng mức cost quan sát như dự đoán chắc chắn cho một run mới với cache khác. Không đồng nhất các con số trên với hóa đơn tài khoản.

| Stage | Latency trung bình | Trung vị | Min–max | Timeout | Incomplete |
|---|---:|---:|---|---:|---:|
| Review | 152,006 giây | 146,697 giây | 119,863–184,314 | 0/5 (0%) | 0/5 (0%) |
| Chat | 14,552 giây | 14,525 giây | 2,656–31,224 | 0/20 (0%) | 0/20 (0%) |

Vì không có completion failure, latency của mọi attempt và latency của successful attempts trùng nhau. Raw usage/cache/reasoning và latency từng lượt đều có trong [summary](../data/academic_benchmark/evaluations/reasoning-five-jds-20261013/summary.json) và traces; không có hidden reasoning content được đưa vào giao diện hoặc báo cáo.

## F. Khuyến nghị

1. **GPT-5.4 high đủ tin cậy cho Initial Review chưa?** Đây là ứng viên tốt trong mẫu: 5/5 hoàn tất, 0 P0 quan sát, 1 P1 về compound coverage. Chưa đủ để bảo đảm độ tin cậy toàn bộ 15 JD, nhiều lần chạy hoặc các JD ngoài mẫu. Có thể tiếp tục dùng làm cấu hình ứng viên với kiểm tra evidence/coverage.
2. **32.768 output tokens và 360 giây đã giải quyết completion failures trước đây chưa?** Run này không timeout/incomplete. JD01 trước timeout 180 giây, nay hoàn tất 135,749 giây; một lần chạy không chứng minh nguyên nhân. JD07 cần 184,314 giây, cho thấy headroom trên 180 có ích trong mẫu. Mọi Review mới chỉ dùng 10.323–14.311 output tokens, đều dưới ceiling cũ 16.384; vì vậy **chưa có bằng chứng riêng rằng tăng output ceiling tạo ra cải thiện**. Giữ 360/32.768 như cấu hình đã đo được, không gọi là tối ưu.
3. **Mini medium phù hợp cho Chat chưa?** Completion và latency tốt: 20/20, trung bình 14,6 giây. Named technologies, SQL bands và API sources được phân biệt tốt, nhưng 3 P0 exact-attribution khiến model **chưa đủ cho giải thích học thuật tự động không kiểm tra**. Effort medium không bảo đảm grounding hoặc summary accuracy.
4. **Kết hợp hai model có giảm lỗi nghiêm trọng không?** Có dấu hiệu giảm các patterns cũ ở Review và ba lượt Chat đầu cùng năm JD. Vẫn có P0 mới trong session/history riêng. Chỉ kết luận quan sát; không gán causal improvement cho model, metadata hoặc effort từ ma trận không có đối chứng.
5. **Cần backend grounding controls không?** Có. Validator hiện kiểm tra source existence/uniqueness, không kiểm tra quan hệ claim→description. Các bước ưu tiên để thiết kế ở đợt sau là lấy score/band trực tiếp từ nguồn khi hiển thị, đối chiếu trích dẫn nguyên văn với đúng CLO, giữ claim-source mapping rõ và recheck summaries/named technologies/learning verbs. Chưa triển khai các controls mới trong run này; sửa prompts hoặc thêm judge giữa benchmark sẽ làm sai phép đo đã đóng băng.
6. **Sẵn sàng classroom MVP chưa?** Phù hợp demo/pilot có giảng viên hoặc reviewer kiểm tra, hiển thị nguồn và ghi rõ giới hạn hồ sơ học thuật. **Chưa nghiệm thu cho tư vấn tự động được coi là authoritative**, vì 3/5 case có Chat P0 và model có thể tạo lỗi mới trong summary dù Review đúng. Reliability kỹ thuật là cần thiết nhưng không thay semantic acceptance; Review khoảng 2,5 phút cũng cần được tính vào cách vận hành demo.

Task engineering và benchmark đã hoàn tất; kết luận semantic giữ đầy đủ lỗi. Mẫu năm JD/một pipeline mỗi JD không kiểm định toàn bộ 15 JD, nhiều lượt chạy, repair có seed sai hoặc deployment readiness ở quy mô lớp học. Không có generation dự phòng, LLM judge hoặc output được sinh lại để chọn kết quả tốt.
