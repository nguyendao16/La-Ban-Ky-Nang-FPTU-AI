# SkillBridge V1 — Metadata và reasoning models

Đã triển khai profile enrichment, evidence metadata và cấu hình model/reasoning riêng cho Review/Chat. **Nghiệm thu kỹ thuật đạt; chưa nghiệm thu semantic toàn bộ output đã thử.** Run `metadata-models-20261013`, ngày 13/10/2026, múi giờ Asia/Bangkok, dùng đúng **12 generation + 12 preflight**, không SDK retry và không sinh lại condition thất bại. Có **6/9 output có text hoàn tất chứa P0**; ba response không hoàn tất không được coi là lỗi reasoning học thuật.

## A. Profile enrichment

Builder thực tế trong `scripts/clo_scoring.py` bổ sung metadata sau khi scoring hiện có tạo CLO. Helper mới `scripts/course_metadata.py` kiểm tra JSON, trường chuỗi, duplicate keys và exact subject_code; giữ toàn bộ source fields/values. `scripts/build_student_academic_profile.py` hiển thị coverage/lỗi. Consumer trong `scripts/academic_review.py` nhận metadata tùy chọn; `scripts/academic_chat.py` giữ nguồn/fingerprint/session isolation.

Schema đầu ra:

```json
{
  "profile_type": "academic",
  "courses": [{
    "course_code": "ADY201m",
    "metadata": {
      "syllabus_name": "giá trị nguồn",
      "course_name_english": "giá trị nguồn",
      "subject_code": "ADY201m",
      "description": "giá trị nguồn",
      "tools": "chuỗi raw nguồn"
    },
    "clos": [{"clo": "CLO1", "description": "giữ nguyên", "score": 8.3, "achievement": "good"}]
  }]
}
```

Profile mới [student_academic_profile.enriched.json](../data/student_academic_profile.enriched.json) có **15 môn, 122 CLO, 15/15 metadata đúng môn**. So sánh projection trên mọi trường gốc khớp hoàn toàn: mã/thứ tự môn, mã/thứ tự CLO, description, score, achievement. Không đổi assessment grades, công thức/threshold hoặc metadata gốc. Bốn môn `MAE101`, `CSI106`, `AIG202c`, `ITE303c` giữ `tools=""`. Không có metadata thiếu/hỏng/mismatch trong 15 môn được chọn. Môn ngoài danh sách không được nạp.

Profile UTF-8 tăng từ **47.495 lên 62.415 bytes**. Với cùng GPT-4.1, prompt/schema/JD/temperature/output budget, input tăng **2.986 tokens**:

| Cặp | Legacy input | Enriched input | Tăng |
|---|---:|---:|---:|
| JD01 | 13.065 | 16.051 | 22,85% |
| JD05 | 13.096 | 16.082 | 22,80% |

Đây là mức tăng toàn request do đổi riêng profile, không phải so prompt mới với benchmark lịch sử. [Validation artifact](../data/academic_benchmark/profile_enrichment_validation.json) và [scoring report mới](../data/clo_scoring_report.enriched.json) lưu kiểm tra. Profile legacy/historical manifest không đổi. **338 file nguồn/lịch sử được bảo vệ khớp hash**; xem [integrity check](../data/academic_benchmark/evaluations/metadata-models-20261013/integrity_check.json).

Metadata lỗi ở dữ liệu tương lai: vẫn giữ môn/CLO, bỏ metadata lỗi, ghi validation report và cảnh báo CLI. Output ghi atomic replace với temporary file riêng và cleanup; lỗi không làm hỏng output cũ. CLI paths cũ giữ tương thích; dùng `--output`/`--profile` để chọn enriched, tránh ghi đè snapshot. Session đang mở/resume không tự thay profile: fingerprint mismatch vẫn yêu cầu phiên mới.

Evidence giữ nguyên dạng CLO và thêm dạng `{"course_code":"ADY201m","metadata_field":"tools"}`. `metadata_field` chỉ nhận description/tools có giá trị không rỗng. Không chấp nhận trộn clo/metadata_field, course/CLO giả hoặc reference trùng. Description có thể hỗ trợ covered cho **kiến thức đúng phạm vi curriculum**; tools-only tối đa related. Score/achievement vẫn cần CLO thật. Metadata chứng minh phạm vi học phần, không chứng minh sinh viên dùng mọi tool hoặc có kinh nghiệm nghề nghiệp. Prompt dùng chung mới ở `scripts/academic_metadata_prompt.py`; cả hai prompt Review/Chat đã cập nhật source interpretation.

## B. Model support và cấu hình

Registry mới `scripts/openai_model_config.py` dùng đúng alias/snapshot đã xác nhận:

| Model | Snapshot | Context | Output tối đa |
|---|---|---:|---:|
| gpt-4o-mini | gpt-4o-mini-2024-07-18 | 128.000 | 16.384 |
| gpt-4.1 | gpt-4.1-2025-04-14 | 1.047.576 | 32.768 |
| gpt-5.4 | gpt-5.4-2026-03-05 | 1.050.000 | 128.000 |
| gpt-5.4-mini | gpt-5.4-mini-2026-03-17 | 400.000 | 128.000 |

Effort GPT-5.4/Mini: `none`, `low`, `medium`, `high`, `xhigh`. Legacy không gửi reasoning và từ chối effort tường minh. Không suy support từ name prefix; model/snapshot chưa xác nhận bị chặn trước HTTP, kể cả có context override. Nguồn: [GPT-4o Mini](https://developers.openai.com/api/docs/models/gpt-4o-mini), [GPT-4.1](https://developers.openai.com/api/docs/models/gpt-4.1), [GPT-5.4](https://developers.openai.com/api/docs/models/gpt-5.4), [GPT-5.4 Mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini).

Settings thêm stage, reasoning_effort, max_output_tokens. Model priority: CLI → biến stage → OPENAI_MODEL → MODEL → gpt-4o-mini. Review/Chat có biến `OPENAI_REVIEW_MODEL`/`OPENAI_CHAT_MODEL`, `*_REASONING_EFFORT`, `*_MAX_OUTPUT_TOKENS`; CLI thêm `--model`, `--reasoning-effort`, `--max-output-tokens`. Cấu hình `.env` hiện tại `MODEL=gpt-5.4` được giữ nguyên, nên muốn Chat dùng Mini phải override stage qua env/CLI. README và `.env.example` đã cập nhật.

Defaults reasoning: Review high/16.384, Chat medium/8.192; legacy 4.096. **Đây là defaults khởi điểm, chưa chứng minh tối ưu hay đủ reliability.** Temperature bỏ trống khác temperature tường minh, kể cả 0. Legacy mặc định gửi 0.0; GPT-5.4 effort none cũng hỗ trợ temperature. Reasoning khác none bỏ temperature mặc định và từ chối override trước HTTP. Mini V1 không cho custom temperature do chưa xác nhận riêng support. [Parameter compatibility](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.4).

SDK 2.54.0 hiện có hỗ trợ reasoning trong parse và input_tokens.count. Cả preflight/generation dùng cùng model/reasoning/schema; context cộng output budget thực, không cắt dữ liệu. Giữ Pydantic/Structured Outputs, store=False, truncation disabled, một generation mỗi Review hoặc lượt Chat. Timeout 180s khi bật reasoning, 60s ở cấu hình khác. Ứng dụng giữ tối đa hai SDK retry lỗi tạm thời; phase comparison tắt retry. Budget/incomplete/refusal/schema/reference/API errors không commit output/turn dở dang.

## C. Evaluation

**283 pytest passed**, `pip check` không có dependency hỏng. Test bao gồm raw/empty/malformed/mismatch metadata, dữ liệu CLO không đổi, deterministic/atomic write, legacy/enriched contexts, hai loại refs, coverage constraint, session fingerprint/persistence, stage/env/CLI precedence, capabilities/snapshots/temperature, output/context boundary, incomplete/API errors và full 12-condition matrix bằng HTTP mock. Test mock không chứng minh semantic correctness. Các test unknown-model và temperature mặc định đã được chỉnh theo contract mới; CLI tests mock settings tại CLI, không phụ thuộc `.env` thật.

Runner cũ được mở rộng phase comparison; logic tập trung ở `scripts/academic_model_comparison.py`, tái sử dụng EvaluationRun, BudgetTransport, RecordingClient. [Ma trận đã khóa](../data/academic_benchmark/metadata_models_plan.json) có 8 Review JD01/JD05 và 4 Chat frozen JD11. Tất cả Review dùng 16.384, Chat dùng 8.192 output ceiling. Data effect chỉ đổi profile trong cặp GPT-4.1; model comparison dùng cùng enriched profile/prompt/schema/JD. Chat giữ cùng Review/history trước lượt 5 và cùng probe; không phải end-to-end pipeline mới. Mini low/medium khác duy nhất effort trong cấu hình generation. Không có LLM judge, classifier, formatting hoặc validation request phụ.

| Condition / trace | Schema/evidence hoặc completion | Semantic đọc thủ công | Latency lượt | Cost usage đã biết |
|---|---|---|---:|---:|
| [review-JD01-legacy-gpt41](../data/academic_benchmark/evaluations/metadata-models-20261013/requests/review-JD01-legacy-gpt41.json) | ref sai | P0, P1 | 18.6s | $0.044386 |
| [review-JD01-enriched-gpt41](../data/academic_benchmark/evaluations/metadata-models-20261013/requests/review-JD01-enriched-gpt41.json) | passed | P0, P1 | 13.9s | $0.049286 |
| [review-JD01-enriched-mini-high](../data/academic_benchmark/evaluations/metadata-models-20261013/requests/review-JD01-enriched-mini-high.json) | incomplete | Không chấm: chưa có text hoàn tất | 77.7s | $0.085765 |
| [review-JD01-enriched-gpt54-high](../data/academic_benchmark/evaluations/metadata-models-20261013/requests/review-JD01-enriched-gpt54-high.json) | timeout | Không chấm: chưa có text hoàn tất | 180.6s | Chưa có usage |
| [review-JD05-legacy-gpt41](../data/academic_benchmark/evaluations/metadata-models-20261013/requests/review-JD05-legacy-gpt41.json) | passed | P0, P1 | 11.9s | $0.021752 |
| [review-JD05-enriched-gpt41](../data/academic_benchmark/evaluations/metadata-models-20261013/requests/review-JD05-enriched-gpt41.json) | passed | P0, P1 | 10.2s | $0.023324 |
| [review-JD05-enriched-mini-high](../data/academic_benchmark/evaluations/metadata-models-20261013/requests/review-JD05-enriched-mini-high.json) | incomplete | Không chấm: chưa có text hoàn tất | 102.0s | $0.075247 |
| [review-JD05-enriched-gpt54-high](../data/academic_benchmark/evaluations/metadata-models-20261013/requests/review-JD05-enriched-gpt54-high.json) | passed | Không ghi nhận P0/P1/P2 | 167.5s | $0.210216 |
| [chat-JD11-gpt41](../data/academic_benchmark/evaluations/metadata-models-20261013/requests/chat-JD11-gpt41.json) | passed | P0, P1, P2 | 8.9s | $0.055844 |
| [chat-JD11-mini-low](../data/academic_benchmark/evaluations/metadata-models-20261013/requests/chat-JD11-mini-low.json) | passed | P1, P2 | 16.3s | $0.025629 |
| [chat-JD11-mini-medium](../data/academic_benchmark/evaluations/metadata-models-20261013/requests/chat-JD11-mini-medium.json) | passed | P1, P2 | 27.3s | $0.034499 |
| [chat-JD11-gpt54-medium](../data/academic_benchmark/evaluations/metadata-models-20261013/requests/chat-JD11-gpt54-medium.json) | passed | P0, P1, P2 | 91.0s | $0.149765 |

Có **9 schema passed**, **8 evidence/technical passed**; một Review legacy bị chặn vì metadata reference không tồn tại. Hai Mini high đã dùng toàn bộ **16.384 output tokens cho reasoning**, không có JSON hiển thị. GPT-5.4 high ở JD01 timeout 180s, không trả usage; run được tiếp tục đúng một lần để chạy condition chưa thử. Mỗi condition có đúng một generation HTTP. Exit code 1 phản ánh failures đã ghi nhận, không có condition bị bỏ khỏi ma trận. Raw timeout trace dùng message chung cũ “sau retry”; ledger chứng minh không retry, và message hiện tại đã sửa thành trung tính.

| Condition | Input | Cached input | Output (gồm reasoning) | Reasoning |
|---|---:|---:|---:|---:|
| review-JD01-legacy-gpt41 | 13065 | 0 | 2282 | 0 |
| review-JD01-enriched-gpt41 | 16051 | 0 | 2148 | 0 |
| review-JD01-enriched-mini-high | 16049 | 0 | 16384 | 16384 |
| review-JD01-enriched-gpt54-high | — | 0 | — | — |
| review-JD05-legacy-gpt41 | 13096 | 12160 | 1725 | 0 |
| review-JD05-enriched-gpt41 | 16082 | 15232 | 1751 | 0 |
| review-JD05-enriched-mini-high | 16080 | 15616 | 16384 | 16384 |
| review-JD05-enriched-gpt54-high | 16080 | 15104 | 13600 | 11584 |
| chat-JD11-gpt41 | 22274 | 0 | 1412 | 0 |
| chat-JD11-mini-low | 22280 | 0 | 1982 | 65 |
| chat-JD11-mini-medium | 22280 | 0 | 3953 | 2070 |
| chat-JD11-gpt54-medium | 22280 | 0 | 6271 | 2542 |

Usage trả về cho **11/12 requests**: **195.617 input**, **58.112 cached input**, **67.892 output**, trong đó **49.029 reasoning**, tổng **263.509 tokens**. Không cộng preflight thành generation usage, không cộng reasoning lần hai vào output/cost.

Cost standard từ usage đã biết khoảng **0,775712 USD**. Request timeout giữ reservation tối đa **0,285883 USD**; cộng phần này được trần ước tính **1,061595 USD** theo giá standard và ceilings đã gửi. Ledger bảo lưu tổng worst-case **1,780083 USD**, thấp hơn ngân sách **2,50 USD**. Đây không phải hóa đơn và không coi timeout là miễn phí. Giá /1M input/cached/output: GPT-4.1 $2/$0.50/$8; Mini $0.75/$0.075/$4.50; GPT-5.4 $2.50/$0.25/$15, kiểm tra ngày 13/10/2026 qua các trang model chính thức nêu trên. Latency gồm preflight/generation và thao tác local của lượt, không phải thời gian model riêng.

Các findings chính, giữ nguyên outputs và chấm theo P0/P1/P2 hiện có:

- **GPT-4.1 Review:** còn attribution thiếu/sai cho PCA/optimization/dashboard/API, sai nhãn CSD203/CLO1 hoặc DAP391m/CLO1, gộp AIL303m/CLO10 basic thành good/excellent, và kết luận SQL tổng thể basic. Metadata làm reference được nhận ở JD01 enriched nhưng không loại các P0; không thể khẳng định thêm metadata tự nó sửa reasoning.
- **GPT-5.4 high Review JD05:** không ghi nhận P0/P1/P2 trong output này. Đúng các score/bands, statistics/hypothesis/PCA/optimization, Python OR R và SQL/BI preferred. AIG202c/CLO2 đúng là Explain ML/DL/Neural Networks 8.0/good; không được nói DL hoàn toàn vắng profile. DAP391m description được dẫn đúng cho dashboard curriculum. Tuy vậy JD01 timeout làm reliability chưa đạt.
- **GPT-4.1 Chat:** lặp claim API ở ADY201m/CLO7; canonical CLO7 không nêu API. Danh sách tools được giải thích có giới hạn, nhưng không sửa đủ history và bỏ sót một số nguồn được yêu cầu.
- **Mini low/medium Chat:** không ghi nhận P0 trong hai output; còn P1 về nhóm DAP391m/CLO7 dưới API mà chưa sửa rõ. Medium nói rõ API nằm ADY201m/CLO5, dẫn CLO3 đúng và giữ điểm/bands, tốt hơn low ở correction/reference. Medium có đề nghị CV review ngoài scope; low thiếu CLO3 reference. Cả hai còn lặp và thêm lời chào/kết luận không cần thiết (P2).
- **GPT-5.4 medium Chat:** sửa rõ ADY201m/CLO7/DAP391m/CLO7 không phải API; đúng API CLO5/CLO6 và điểm. Nhưng đoạn CPV gộp “học và triển khai ... segmentation ... tracking” làm mạnh Understand/Explain ở CPV301/CLO5/CLO9 và chỉ dẫn metadata.tools; P0 còn tồn tại. Đoạn PFP nêu nội dung đúng nhưng thiếu CLO refs (P1), trình bày lặp (P2).

**Metadata có tác dụng hữu ích về curriculum/tools:** các Chat thừa nhận Git/GitHub/JupyterLab/RStudio/Watson, SQL Server, VS Code/Colab và PyCharm-or-MATLAB đúng nguồn; textbook/Internet được coi là học liệu. Không kết luận student dùng mọi tool. SQL Server có thêm evidence CLO5/CLO6 trực tiếp, mạnh hơn metadata đơn thuần. Tuy nhiên không có cặp Chat legacy/enriched để định lượng riêng cải thiện tools; các model Chat đều dùng cùng enriched profile. Không thể tách tác động metadata khỏi prompt mới bằng benchmark lịch sử.

[Manual assessments](../data/academic_benchmark/evaluations/metadata-models-20261013/manual_assessments.json) ghi từng finding/score và hashes; [summary](../data/academic_benchmark/evaluations/metadata-models-20261013/summary.json) ghi metric/comparability/cost; [4 Review export](../data/academic_benchmark/initial_reviews/metadata-models-20261013/index.json) giữ các response vượt validation mà không gọi API thêm. Schema-valid Review GPT-4.1 trong export vẫn có P0, không phải mẫu đã nghiệm thu.

## D. Khuyến nghị và giới hạn

Cấu hình **ứng viên sơ bộ**, ưu tiên correctness/grounding trước cost:

```dotenv
OPENAI_REVIEW_MODEL=gpt-5.4
OPENAI_REVIEW_REASONING_EFFORT=high
OPENAI_REVIEW_MAX_OUTPUT_TOKENS=16384
OPENAI_CHAT_MODEL=gpt-5.4-mini
OPENAI_CHAT_REASONING_EFFORT=medium
OPENAI_CHAT_MAX_OUTPUT_TOKENS=8192
```

Review GPT-5.4 high là ứng viên chất lượng tốt nhất trong **một ca hoàn tất**, nhưng chỉ hoàn tất 1/2 JD ở timeout 180s; chưa thể chọn cấu hình Review đạt reliability. Ca JD05 dùng 13.600 output, gồm 11.584 reasoning, khoảng 167,5s/$0,2102. Ceiling 16.384 đủ ca này nhưng không chứng minh đủ mọi JD. Không khuyến nghị Mini high/16.384 cho Review vì 2/2 budget-incomplete, 77,7–102,0s, không có visible output. Nếu tiếp tục thử high cần một đợt mới với output/timeout lớn hơn hoặc effort thấp hơn; các giá trị đó chưa được đo và không được tự chạy trong ngân sách hiện tại. Tài liệu [reasoning](https://developers.openai.com/api/docs/guides/reasoning) cũng lưu ý reasoning dùng output budget và đề xuất buffer ban đầu lớn hơn.

Chat Mini medium là lựa chọn sơ bộ cho follow-up thường: correction tốt hơn low ở context này, giá khoảng **$0,0345/27,3s** so với low **$0,0256/16,3s**. Ceiling 8.192 đủ hai reply này; medium dùng 3.953 output, gồm 2.070 reasoning. Nâng effort cải thiện một số correction/reference, chưa loại P1 và chưa chứng minh xu hướng tổng quát. GPT-5.4 medium sửa SQL/API rõ hơn nhưng khoảng **$0,1498/91,0s** và vẫn có peripheral CV P0; không có cơ sở dùng nó mặc định cho mọi Chat chỉ vì model lớn hơn.

Chưa có đối chứng effort Review, control JD thành công/low-overlap, nhiều lần lấy mẫu hoặc pipeline conversation mới. Chỉ một profile, một output/condition, một người chấm và một frozen Chat chứa lỗi lịch sử. Metadata-only description covered là curriculum coverage, không có score tương ứng hay bằng chứng personal tool proficiency. Identifier validation không xác minh từng clause đúng ngữ nghĩa. **Chưa được giới thiệu toàn bộ hệ thống là đã đạt semantic acceptance**; các P0/P1 được giữ để tiếp tục nghiên cứu theo ngân sách mới được duyệt.

Các thay đổi còn lại: CLI Review/Chat, runner, README, `.env.example`, ba test files cũ và hai test files mới; không thêm dependency, frontend, scoring/skill taxonomy, RAG/vector DB, agents hoặc LLM judge. `.env`, dữ liệu grades/course metadata, profile/reviews/JDs/annotations lịch sử giữ nguyên.
