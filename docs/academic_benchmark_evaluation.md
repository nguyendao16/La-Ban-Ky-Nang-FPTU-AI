# SkillBridge V1 — Benchmark JD thực tế và grounding

**Kết luận nghiệm thu: cần sửa grounding trước khi chấp nhận.** Đã triển khai benchmark 15 JD, cấu hình temperature và hướng dẫn đối chiếu claim/CLO; chạy một đợt live đủ 78 generation, đọc thủ công cả 78 output. Có **30 output chứa P0**, trong đó **11/15 Initial Review** và **19/53 lượt chat cơ bản/sâu**. Mọi output đều vượt qua kiểm tra JSON/schema/identifiers, nhưng điều đó không chứng minh diễn giải học thuật đúng. Giữ mặc định **temperature 0.0**; dữ liệu A/B chưa đủ điều kiện đề xuất 0.3.

Run `internship-20261013`, nguồn **live**; bắt đầu `2026-10-13T14:45:56.922476+07:00`, kết thúc inference `2026-10-13T15:05:07.571978+07:00`. Requested model `gpt-4.1`, resolved model của cả 78 generation `gpt-4.1-2025-04-14`. Không sửa `.env`. Annotations là đánh giá thủ công của Codex sau đọc output và description, chưa có người đánh giá độc lập thứ hai.

## 1. Nguồn JD và giới hạn provenance

Giữ JD00–JD14 đúng danh sách yêu cầu, **không thay posting**. JD00 sao chép nguyên byte từ `data/sample_jd.txt`, là mẫu nội bộ. JD01–JD14 là `sourced_paraphrase`: viết lại nội dung đã kiểm tra, không phải bản nguyên văn do nhà tuyển dụng chứng thực. Có sáu nguồn HTML đọc trực tiếp, một PDF đọc text và bảy posting kiểm tra qua chỉ mục tìm kiếm khi trang ATS là JavaScript shell hoặc không đọc được. Mọi nguồn được kiểm tra ngày **13/10/2026**; không khẳng định vị trí còn mở.

| Case | Company / role | Nhóm | Truy xuất | Nguồn thực tế |
| --- | --- | --- | --- | --- |
| JD00 | SkillBridge — Computer Vision Intern — local baseline | computer_vision | `local_file` | [Mẫu nội bộ](../data/academic_benchmark/jds/JD00.txt) |
| JD01 | VNG GreenNode — AI Intern | computer_vision | `direct_html` | [employer_site](https://career.vng.com.vn/en/job-search/detail/6901-ai-intern-greennode) |
| JD02 | FPT Software — Intern AI / Perception Engineer | computer_vision | `direct_html` | [university_repost](https://forum.uit.edu.vn/t/fpt-software-tuyen-dung-intern-ai-computer-vision-uav-robotics/161000) |
| JD03 | Phần mềm Hoàn Cầu — Computer Vision Intern | computer_vision | `direct_html` | [job_board](https://www.topcv.vn/viec-lam/thuc-tap-sinh-computer-vision/2212732.html) |
| JD04 | Bosch — Industrial AI Engineer Intern | industrial_ai | `direct_html` | [job_board](https://www.iagora.com/work/en/offer/internship-vietnam-engineering/6389924) |
| JD05 | Sapo — Data Analyst Intern (Fulltime) | data_analytics | `direct_html` | [employer_site](https://tuyendung.sapo.vn/co-hoi-viec-lam/sapo-internship-2026-thuc-tap-sinh-data-analyst-fulltime-a3824.html) |
| JD06 | VNGGames — Data Analysis Intern | data_analytics | `search_index` | [employer_site](https://career.vng.com.vn/tim-kiem-viec-lam/chi-tiet/6700-data-analysis-intern-vnggames-vi?isShowForm=1) |
| JD07 | Kyanon Digital — Data Analyst Intern — K-Fresh Trainee | data_analytics | `direct_pdf_text` | [employer_pdf](https://kyanon.digital/wp-content/uploads/2026/02/202602-Intern-Data-Analyst-K-Fresh-Trainee.pdf) |
| JD08 | Razer — Data Scientist Intern (Personalisation) | data_science | `search_index` | [employer_ats](https://razer.wd3.myworkdayjobs.com/en-US/Careers/job/Data-Scientist-Intern_JR2026007105) |
| JD09 | Poshmark — AI/ML Engineering Intern (Summer 2026) | machine_learning | `search_index` | [employer_ats](https://jobs.ashbyhq.com/poshmark/0eee9939-6306-47a2-9b24-8cb7bf1dec71/) |
| JD10 | VNGGames — AI Engineer Intern | generative_ai | `search_index` | [employer_site](https://career.vng.com.vn/tim-kiem-viec-lam/chi-tiet/6783-ai-engineer-intern-vnggames-vi) |
| JD11 | Tessera Labs — Software Engineering Intern, Backend | backend | `search_index` | [employer_ats](https://jobs.ashbyhq.com/tessera-labs/dce8d8e5-f169-4bdb-b1c2-f4754fca31e7?src=LinkedIn) |
| JD12 | Jua — Data Engineering Intern | data_engineering | `search_index` | [employer_ats](https://jobs.ashbyhq.com/jua/9d21aa2a-99c5-4133-a569-c42493f4cc8c) |
| JD13 | VSEC — Security Monitoring Intern | security | `direct_html` | [job_board](https://www.topcv.vn/viec-lam/thuc-tap-sinh-giam-sat-an-toan-thong-tin/1800286.html) |
| JD14 | GrayMatter Robotics — 2026 Fall Robotics Engineering Intern: Systems & Applications | robotics | `search_index` | [employer_ats](https://jobs.ashbyhq.com/graymatter-robotics/03158f09-4bc0-4d9b-b288-996193db190a) |

[Manifest](../data/academic_benchmark/manifest.json) ghi requested/actual URL, category, ngày kiểm tra, source/snapshot type, phương thức truy xuất, hash và limitations từng nguồn. Với VNG, URL tiếng Việt được dùng khi URL tiếng Anh không render; Tessera dùng chính posting có query `src=LinkedIn`. Đây là thay đường truy xuất, không thay công việc. Các JD06/08/09/10/11/12/14 chỉ xác nhận text được chỉ mục của đúng posting: có thể thiếu section hoặc không phản ánh lần cập nhật sau; không coi chúng là employer-exact snapshot.

Fixtures giữ qualifications, preferred skills, responsibilities, learning opportunities và employer-stack context riêng. JD02 chỉ dùng AI/Perception cùng điều kiện chung áp dụng, bỏ yêu cầu riêng vai trò UAV/Robotics khác. Sapo giữ Python **OR** R, SQL/BI là preferred; Bosch ONNX là điểm cộng; Jua SQL/Docker/orchestration là nice-to-have. Razer learning outcomes không thành năng lực đã phải có; stack Poshmark không thành danh sách bắt buộc. Dấu slash/danh sách công nghệ không đủ rõ được ghi là chưa rõ, không tự chuyển thành AND hoặc OR. GPA/English được giữ khi có nhưng không suy từ CLO. Expected behaviors/references được viết sau đọc profile; runner chỉ gửi `user` của các câu hỏi, không gửi đáp án expected hoặc rubric.

## 2. Thay đổi và kiểm thử kỹ thuật

| File / nhóm | Thay đổi |
| --- | --- |
| [scripts/academic_review.py](../scripts/academic_review.py) | ReviewSettings.temperature=0.0; load_settings thêm keyword; finite [0,2], reject bool/NaN/infinity; helper truyền vào generation đã xác nhận tương thích. |
| [scripts/review_academic_profile.py](../scripts/review_academic_profile.py) | CLI --temperature, giữ mọi option/default còn lại. |
| [scripts/chat_academic_profile.py](../scripts/chat_academic_profile.py) | CLI --temperature, giữ API session và persistence. |
| [scripts/academic_review_prompt.py](../scripts/academic_review_prompt.py) | Claim→description→CLO; learning verbs/achievement riêng; named tech, summary, AND/OR, preferred và task/context được kiểm tra nội bộ. |
| [scripts/academic_chat_prompt.py](../scripts/academic_chat_prompt.py) | Cùng grounding; history chỉ ngữ cảnh, summary phải đối chiếu lại; cho phép chủ đề học có điều kiện nếu chưa học ngoài trường, trình bày linh hoạt. |
| [scripts/academic_chat.py](../scripts/academic_chat.py) | Chỉ đổi description trường reply theo hướng dẫn mới; tên/kiểu/constraints không đổi. |
| [scripts/evaluate_academic_benchmark.py](../scripts/evaluate_academic_benchmark.py) | Runner phase/case/run ID, live opt-in, POSIX run lock, raw trace, physical HTTP budget, resume phần đã hợp lệ và frozen A/B. |
| [tests/test_academic_benchmark.py](../tests/test_academic_benchmark.py) | 37 tests offline bổ sung, SDK mocks và chặn HTTP thật. |
| [data/academic_benchmark/](../data/academic_benchmark/) | 15 fixtures, manifest, 15 review mới, 15 conversation, requests/raw traces, rubric, annotations, summary và integrity. |
| [README.md](../README.md) | Cấu hình temperature, scope mới, hướng dẫn benchmark và kết quả quan sát. |
| [docs/academic_benchmark_evaluation.md](../docs/academic_benchmark_evaluation.md) | Báo cáo hiện tại; giữ nguyên báo cáo và transcript cũ. |

**Pytest: 238 passed** (201 baseline + 37 mới), chạy toàn suite `.venv/bin/python -m pytest -q`; riêng benchmark 37 passed. `pip check`: không có dependency hỏng. Python 3.14.4, OpenAI SDK 2.54.0, Pydantic 2.14.1, pytest 9.1.1; không thêm dependency ngoài môi trường hiện có. Tests mock chỉ xác minh cơ chế, không chứng minh model tuân thủ grounding hoặc scope.

Tests mới kiểm tra manifest/hash/provenance, mapping JD–review, đúng thứ tự history và evidence assistant, một generation mỗi lượt, resume không duplicate, giữ failed raw output, malformed response/evidence không commit history, không overwrite trace, source thay đổi bị chặn trước request, run lock độc quyền và budget không reset khi resume. HTTP mock trả lỗi 500 để xác minh retry vật lý cũng bị trần budget chặn trước dispatch; lỗi authentication không ghi message có key. A/B tests kiểm tra toàn bộ input/instructions/schema/model/output budget/store/truncation giữ nguyên, chỉ temperature khác. Các tests cũ tiếp tục kiểm tra loaders, refusal/incomplete/schema, context và persistence rollback/isolation.

Đối chiếu SHA-256 trước/sau: **30 file được bảo vệ không đổi**, gồm profile, academic/scoring reports, scoring/profile-builder logic, `.env`, JD/review gốc và tất cả historical transcripts/fixtures. [Integrity artifact](../data/academic_benchmark/evaluations/internship-20261013/integrity_check.json) lưu hash trước/sau. Review schema giữ nguyên hoàn toàn; Chat schema giữ nguyên cấu trúc/constraints, chỉ description đã thay theo plan. Profile vẫn 15 môn, 122 CLO; SHA-256 `99f34048ed8c3d11ed972fa0a97476aa7fba6f071ad8aea454bb66b6b5c2eca1`. Không thay Scoring Engine, dữ liệu học thuật hoặc triển khai persistence.

Temperature nhận số hữu hạn `[0,2]`, mặc định `0.0`. Các alias/snapshot đã xác nhận cho gpt-4o-mini và gpt-4.1 truyền nhiệt độ vào generation. Model chưa xác nhận không cho override khác 0.0 trước request; mặc định giữ hành vi cũ bằng cách không gửi temperature. Input counting không nhận temperature. Khoảng API tham chiếu [OpenAI Responses API](https://developers.openai.com/api/reference/python/resources/responses/methods/create). Model priority `OPENAI_MODEL → MODEL → gpt-4o-mini`, timeout 60 giây, tối đa hai SDK retry, 4.096 output tokens và `store=False` không đổi.

## 3. Thực thi live và artifacts

| Phase | Generation đã gửi | Preflight | Nội dung |
| --- | ---: | ---: | --- |
| Regression pilot | 4 | 4 | Hai history contamination seeds từ transcript live cũ; SQL achievement và CV conditional gaps. |
| Initial Review | 15 | 15 | Review mới temperature 0.0 cho từng JD, validate trước chat. |
| Chat cơ bản | 45 | 45 | Ba lượt / JD, session riêng và đầy đủ history. |
| Deep | 8 | 8 | JD02/JD05/JD10/JD11, hai lượt bổ sung mỗi session. |
| A/B candidate | 6 | 6 | Replay frozen lượt follow-up 3 ở 0.3; baseline 0.0 đã có. |
| **Tổng** | **78/80** | **78** | **156 HTTP request, không retry, hai generation dự phòng không dùng.** |

Tổng usage do Responses trả: **1,234,811 input**, gồm **1,125,376 cached input**, và **59,896 output tokens**. Đây là usage generation, không cộng giả token preflight hoặc suy hóa đơn. Không lỗi API/quota/context/refusal/incomplete trong run này; 78/78 schema/references passed. Những lỗi này được kiểm tra offline bằng mock, không gắn nhãn live.

Sau pilot không có P0 được ghi nhận, prompt được chốt trước benchmark chính; cả run dùng cùng fingerprints. Khi benchmark lộ P0, vẫn giữ nguyên output thất bại để đo phạm vi của đợt chạy đã duyệt; không chỉnh prompt rồi lặp suite, không regeneration để chọn câu đẹp. Phần deep/A/B đã định trước hoàn tất trong cùng trần, không dùng hai request dự phòng để thử lại. Không có LLM judge, semantic validator mới, extraction/retrieval hoặc request phân loại/render.

[Run ledger](../data/academic_benchmark/evaluations/internship-20261013/run.json) lưu context fingerprints và từng HTTP dispatch. [Requests](../data/academic_benchmark/evaluations/internship-20261013/requests) giữ instructions/input/schema, raw SDK body, parsed reply/evidence, model, temperature, status, usage và validation result. API errors nếu xảy ra chỉ lưu type/code để không giữ message có credential. [Reviews mới](../data/academic_benchmark/initial_reviews/internship-20261013) và [Conversations mới](../data/academic_benchmark/conversations/internship-20261013) tách khỏi dữ liệu lịch sử. Benchmark bật persistence hiện có trong thư mục artifacts để resume phase; default sản phẩm vẫn là memory-only. History từ session đã lưu được đối chiếu raw trace; candidate 0.3 không ghép vào history 0.0.

## 4. Đánh giá thủ công Review và Chat

Toàn bộ 78 output đã đọc: [Annotations đầy đủ](../data/academic_benchmark/evaluations/internship-20261013/manual_assessments.json) có timestamp, response hash, chín điểm, findings và notes. `0=chưa đạt`, `1=một phần`, `2=đạt`, `null=N/A`. Không cho điểm ở ca chưa đọc; run này không còn ca chưa đọc. Các điểm là nhận xét định tính trong ngữ cảnh cụ thể, không phải tỷ lệ match/tuyển dụng hoặc kiểm định thống kê. [Rubric](../data/academic_benchmark/evaluations/rubric.json) xác định P0/P1/P2; field `semantic_success` trong annotations chỉ có nghĩa **không ghi nhận P0**, không đồng nghĩa nghiệm thu mọi tiêu chí. P1/P2 và điểm vẫn được báo riêng.

| Nhóm output | Đã đọc | Có P0 | Có P1 | Có P2 | Không findings |
| --- | ---: | ---: | ---: | ---: | ---: |
| Pilot | 4 | 0 | 2 | 2 | 1 |
| Review | 15 | 11 | 15 | 3 | 0 |
| Chat cơ bản + sâu | 53 | 19 | 40 | 18 | 7 |
| Candidate 0.3 | 6 | 0 | 3 | 1 | 3 |

Các cột severity có thể cùng xuất hiện ở một output, không cộng thành số output. Chỉ **3/15 phiên benchmark** không ghi nhận P0 trong review và cả chuỗi chat: JD00, JD02, JD13; cả ba còn P1/P2. Không có phiên nào được tuyên bố đạt đầy đủ mọi tiêu chí.

| Case | Initial Review | Chat từng lượt | Điểm đáng chú ý |
| --- | --- | --- | --- |
| JD00 | [review-JD00](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD00.json): Một phần: P1 | 1: Một phần: P1; 2: Một phần: P1; 3: Đạt trong lượt này | CLO8 đúng 8.81/excellent, không suy YOLO; review compound coverage còn rộng. |
| JD01 | [review-JD01](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD01.json): Không đạt: P0 | 1: Không đạt: P0; 2: Không đạt: P0; 3: Không đạt: P0 | Face/tracking gán nhầm CLO8; PCA/hồi quy thiếu CLO đúng; project intended bị kể như CV artifact. |
| JD02 | [review-JD02](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD02.json): Một phần: P1 | 1: Một phần: P1; 2: Một phần: P1; 3: Một phần: P1; 4: Một phần: P1; 5: Một phần: P1 | Framework/OD tách đúng; không làm rõ YOLO là tiền đề từ sinh viên, không nằm JD; summary scope rộng. |
| JD03 | [review-JD03](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD03.json): Không đạt: P0 | 1: Không đạt: P0; 2: Một phần: P1; 3: Đạt trong lượt này | Generic cleaning bị đổi thành image-specific; AIL303m/CLO10 basic bị gộp good/excellent. |
| JD04 | [review-JD04](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD04.json): Không đạt: P0 | 1: Không đạt: P0; 2: Không đạt: P0; 3: Không đạt: P0 | RAG/agent, PCA/SVM và deployment bị gán rộng; academic deployment không phải production. |
| JD05 | [review-JD05](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD05.json): Không đạt: P0 | 1: Một phần: P1; 2: Không đạt: P0; 3: Không đạt: P0; 4: Một phần: P1; 5: Không đạt: P0 | Python OR R/SQL preferred đúng; R trong tool list bị phủ nhận; dashboard/SQL attribution và summary optimization sai. |
| JD06 | [review-JD06](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD06.json): Không đạt: P0 | 1: Không đạt: P0; 2: Không đạt: P0; 3: Không đạt: P0 | Dashboard/Jupyter/Watson sai references; follow-up tiếp tục claim sai từ history. |
| JD07 | [review-JD07](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD07.json): Không đạt: P0 | 1: Không đạt: P0; 2: Một phần: P1; 3: Đạt trong lượt này | DAP391m/CLO1 8.45/good bị gọi excellent; GPA/English không suy từ CLO ở follow-up. |
| JD08 | [review-JD08](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD08.json): Không đạt: P0 | 1: Một phần: P1; 2: Một phần: P1; 3: Không P0/P1; P2 | AIL303m/CLO9 6.87/basic bị gộp good/excellent; feature engineering gán thêm vào ADY201m/CLO7. |
| JD09 | [review-JD09](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD09.json): Không đạt: P0 | 1: Không đạt: P0; 2: Một phần: P1; 3: Đạt trong lượt này | PCA/SVM/hồi quy follow-up đúng; review/turn1 graph/sorting và SVM refs sai. |
| JD10 | [review-JD10](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD10.json): Không đạt: P0 | 1: Không đạt: P0; 2: Một phần: P1; 3: Một phần: P1; 4: Đạt trong lượt này; 5: Đạt trong lượt này | pandas/numpy/JSON/CSV bị nhận là đã học; MCP sai nghĩa; tutorial/injection từ chối đúng. |
| JD11 | [review-JD11](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD11.json): Không đạt: P0 | 1: Một phần: P1; 2: Một phần: P1; 3: Đạt trong lượt này; 4: Không đạt: P0; 5: Một phần: P1 | FastAPI/SQLAlchemy/PostgreSQL không bị suy từ Python/SQL; API gán sai CLO7; summary chưa sửa rõ. |
| JD12 | [review-JD12](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD12.json): Không đạt: P0 | 1: Một phần: P1; 2: Một phần: P1; 3: Không đạt: P0 | GitHub use-at-least-one bị khẳng định đã dùng; SQL nice-to-have thành required; DAP7 bị gán SQL. |
| JD13 | [review-JD13](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD13.json): Một phần: P1 | 1: Một phần: P1; 2: Một phần: P1; 3: Không P0/P1; P2 | OS/network/Python chỉ foundations, không suy SIEM/SOAR/SOC; có evidence omission và lặp. |
| JD14 | [review-JD14](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD14.json): Một phần: P1 | 1: Không đạt: P0; 2: Một phần: P1; 3: Một phần: P1 | Python/math không suy ROS/robot công nghiệp; verb face-recognition bị nâng Explain→Implement; gaps chưa tách đủ. |

Initial Review thường nhận ra đa số công nghệ chưa được xác nhận, nhưng dễ dùng một CLO đúng ID cho phương pháp không có trong description, gộp requirement có phần chưa có bằng chứng thành covered, hoặc summary làm mạnh hơn comment chi tiết. Chat follow-up thường phân biệt foundation/framework đúng, nhưng câu phân tích rộng hoặc summary dễ thêm/giữ attribution sai. Có trường hợp lỗi tự khai/Scope được từ chối đúng trong khi grounding học thuật ở các lượt hợp lệ vẫn sai; đây là hai tiêu chí khác nhau.

## 5. Tám regression được đối chiếu lại

| Regression | Chuẩn từ profile/JD | Quan sát và kết quả |
| --- | --- | --- |
| RG01 SQL/project | ADY201m/CLO7 nêu SQL/database access; DAP391m/CLO7 không nêu. | Pilot sửa đúng; JD05-4 challenge sửa đúng. JD12-3 summary tái gán SQL cho DAP7: P0 còn tồn tại. |
| RG02 named methods | MAI391/CLO5 linear regression; CLO6 PCA; CLO7 SVM. | Pilot CV_METHODS và JD09-3 đúng. Review JD01/04 và JD09-1 còn thiếu/gán sai CLO cho named methods. JD05-5 summary thêm optimization ngoài các references (CLO4 mới đúng). |
| RG03 curriculum vs achievement | DBI202/CLO5–6 5.96/basic; ADY201m/CLO1 8.3/good; CLO7 8.61/excellent. | Pilot/JD05 follow-up không chấm SQL tổng thể và phân biệt curriculum nâng cao với basic. Nhiều lượt so sánh thiếu exact score; review JD11 gọi mọi CLO good/excellent dù DBI basic. Không tính lại điểm. |
| RG04 CV specificity/score | CPV301/CLO8 Understand/Implement object detection: 8.81/excellent; CLO9 Explain face/tracking. | JD00-3 giữ đúng 8.81/excellent, không infer YOLO. JD02-3 frameworks tách đúng. JD01-3 vẫn gán face/tracking cho CLO8 và nâng verb: P0. |
| RG05 academic vs employment | Academic project/deployment không xác nhận production employment; internship tasks không mặc nhiên là prerequisite. | Pilot CV_FRAMEWORKS tách production đúng. JD04 attribution deployment cho DAP7 sai; một số gaps gộp kiến thức và experience, một số intended outcomes bị kể như artifact đã hoàn thành: còn P0/P1. |
| RG06 history/summary | History là context; claim summary phải đối chiếu profile và sửa/bỏ phần trước sai. | Hai historical seeds được sửa ở pilot. JD06-3 lặp dashboard/tools sai; JD05-5 summary thêm optimization sai; JD11-5 không sửa rõ attribution API/CLO7: chưa đạt nhất quán. |
| RG07 AND/OR/preferred/stack | Sapo Python OR R và SQL preferred; Jua SQL preferred; Bosch ONNX plus; stack/learning opportunities không là mandatory. | Sapo follow-up giữ OR/preferred; Jua JD12-3 bịa Required ... SQL và promotion nice-to-have: P1. Một số review covered compound khi còn phần chưa xác nhận. R list biết tool/use-at-least-one vẫn dễ bị diễn giải sai. |
| RG08 security/robotics | CSI106/CLO4 network, CLO5 OS; CEA201/CLO5 OS; Python/math không chứng minh SIEM/SOAR/SOC hoặc ROS/physical robot. | JD13-3 và JD14-3 không infer các công nghệ/experience. Còn evidence omission và gaps grouping; đây là thành công cục bộ, không xóa P0 khác trong case JD14. |

Các description đối chiếu khác: API ở ADY201m/CLO5 và DAP391m/CLO5–6, không nằm trong ADY201m/CLO7 hoặc DAP391m/CLO7; dashboard explicit ở DAP391m/CLO7, không ADY201m/CLO7. ADY201m/CLO3 nêu R/GitHub/Jupyter/RStudio/Watson trong danh sách nhưng chỉ dùng **ít nhất một** tool. DAP391m/CLO1=8.45/good; AIL303m/CLO9=6.87/basic; CLO10=5.42/basic. Generic Python libraries/data import không nêu pandas/numpy/JSON/CSV hoặc image-specific preprocessing. MCP bị model gọi “Multi-Channel Platform”; nghĩa đúng trong ngữ cảnh này là **Model Context Protocol**, được xác nhận trong [OpenAI Docs](https://developers.openai.com/plugins/concepts/mcp-server).

## 6. Temperature A/B trên context giống nhau

Sáu cặp dùng nguyên request của lượt chat 3: cùng profile, JD, review, instructions, schema, history user–assistant thực tế, resolved model, 4.096 output budget và `store=False`; chỉ temperature 0.0→0.3 khác. Context hash kiểm tra bằng request sau bỏ duy nhất field temperature; cả sáu pair `comparable`. Baseline 0.0 đã được dùng từ benchmark, không generation lại. History có thể chứa nhận xét sai trước đó ở cả hai điều kiện, nên thí nghiệm cũng đo khả năng sửa/lặp contamination.

| Pair / nhóm | 0.0 | 0.3 | So sánh thủ công |
| --- | --- | --- | --- |
| JD02 / computer_vision | Một phần: P1 | Một phần: P1 | Academic tương đương; cả hai không sửa ambiguity YOLO trong tiền đề. Naturalness ngang nhau. |
| JD05 / data_analytics | Không đạt: P0 | Một phần: P1 | 0.3 bỏ phủ nhận R của 0.0 nhưng thêm kết luận đáp ứng đủ yêu cầu chính. JD/gap/scope scores giảm; không coi đây là thắng học thuật. |
| JD09 / machine_learning | Đạt trong lượt này | Đạt trong lượt này | Đều đúng MAI391/CLO5–7 và không infer PyTorch; 0.3 bổ sung AIL303m/CLO4 đúng. Không có khác biệt naturalness rõ. |
| JD10 / generative_ai | Một phần: P1 | Một phần: P1 | Đều gọi sai MCP theo history; 0.3 lặp Tóm lại nhiều hơn. Không cải thiện grounding. |
| JD11 / backend | Đạt trong lượt này | Đạt trong lượt này | Đều tách Python/SQL khỏi named frameworks; 0.3 ngắn gọn hơn nhưng cùng naturalness score 2. |
| JD13 / security | Không P0/P1; P2 | Đạt trong lượt này | Đều không infer SIEM/SOAR/SOC; 0.3 bỏ kết luận lặp, naturalness 1→2. |

Trong sáu baseline, 1 output có P0 và 3 có P1; sáu candidate 0.3 không ghi nhận P0 nhưng 3 có P1. Không được suy từ mẫu này rằng 0.3 giảm lỗi nói chung. Completeness scores ngang nhau cả sáu; tự nhiên/ít lặp cải thiện rõ ở JD11 và JD13 (2/6), giảm ở JD10, còn lại không rõ hoặc ngang nhau. JD05 có các tiêu chí JD/gap/scope giảm dù bỏ được một claim sai. Điều kiện cải thiện đa số mà không giảm học thuật chưa đạt; **giữ khuyến nghị 0.0**, không chạy 0.5. Toàn benchmark vẫn có P0 nghiêm trọng ở cả Review/Chat, không thể dùng temperature để tuyên bố giải quyết grounding.

## 7. Vấn đề còn lại và giới hạn quan sát

Vấn đề hệ thống là claim-to-description alignment: valid references không buộc từng ý trong reply phải do CLO đó hỗ trợ. Summary và nhóm nhiều CLO làm mất specificity, verbs hoặc achievement; danh sách “use at least one” bị hiểu như mọi tool hoặc bị phủ nhận hoàn toàn. History được replay đúng về kỹ thuật nhưng model vẫn có thể lặp nội dung sai. Named technology inference, optional promotion và intended-outcome→completed-project chưa được prompt loại bỏ đáng tin.

Một số quan sát cụ thể gồm nghĩa MCP sai, Jua SQL required giả và gán image-specific cleaning cho generic data CLO. Cách trình bày thường còn formal/lặp; missing evidence không bị biến thành actual deficit trong phần lớn follow-up, nhưng kinh nghiệm và knowledge gaps đôi lúc vẫn chung một danh sách. Grade bands sai phải được coi là P0; omission exact score khi so sánh và thiếu reference cho claim đúng được chấm P1 theo rubric. Không tự sửa hoặc loại evidence để làm câu trả lời đạt.

Đánh giá chỉ dùng một Student Profile, một run/model snapshot, một mẫu cho mỗi context, bảy nguồn lấy từ chỉ mục và một người chấm. Temperature 0 không bảo đảm deterministic. Không có đối chứng prompt cũ trên toàn bộ JD cùng context; lịch sử chỉ dùng làm seed kiểm tra correction, không để tuyên bố mức cải thiện tổng thể theo phần trăm. Một refusal đúng không bảo đảm mọi injection sẽ bị chặn. Không kiểm thử tải, multi-user hoặc authentication production; persistence vẫn là prototype local POSIX hiện có.

Nghiệm thu kỹ thuật về artifacts/tests hoàn tất; nghiệm thu chất lượng **chưa đạt** vì P0 còn tồn tại. Có thể dùng bộ benchmark này để nghiên cứu/đối chiếu có người đọc nguồn, nhưng chưa nên giới thiệu output là Academic Advisor đáng tin trong phạm vi đã thử. Bước tiếp theo cần sửa grounding có mục tiêu rồi kiểm tra lại các P0 đã lưu theo ngân sách mới được xác định, không tự chạy lại đợt lớn trong lần bàn giao này.

## 8. Lệnh chạy và resume

Chạy từ root. Không có `--live` chỉ validate fixtures, không tạo SDK client hoặc gửi HTTP:

```bash
.venv/bin/python scripts/evaluate_academic_benchmark.py
.venv/bin/python -m pytest -q
```

Lệnh đã dùng cho run hiện tại; rerun cùng phase/run ID bỏ qua phần hợp lệ đã hoàn thành và không reset budget:

```bash
.venv/bin/python scripts/evaluate_academic_benchmark.py --live --phase pilot --run-id internship-20261013 --max-generations 80
.venv/bin/python scripts/evaluate_academic_benchmark.py --live --phase benchmark --run-id internship-20261013 --max-generations 80
.venv/bin/python scripts/evaluate_academic_benchmark.py --live --phase deep --case JD02 --case JD05 --case JD10 --case JD11 --run-id internship-20261013 --max-generations 80
.venv/bin/python scripts/evaluate_academic_benchmark.py --live --phase temperature --run-id internship-20261013 --max-generations 80
```

Run ID mới tạo một đợt API có phí mới, không phải resume ngân sách cũ. Phải quản lý cùng run ID trong một đợt; `--max-generations` không vượt 80 và không đổi khi resume. `--case` được lặp để chọn case. Resume từ chối thay profile/JD/manifest/prompt/schema/model/budget; hai tiến trình không mở cùng run. Case đã lỗi không tự retry hoặc sinh review thay thế; raw trace được giữ, case còn lại có thể chưa thử. API/quota/budget error dừng phase. Interrupted request trace không bị overwrite; cần đọc ledger/history để phân biệt generation đã trả nhưng chưa commit. CLI exit 0 chỉ nghĩa validation/phase kỹ thuật thành công, không tự nghiệm thu semantic.

Review/Chat CLI nhận `--temperature 0.3` khi muốn override; không cần sửa `.env`:

```bash
.venv/bin/python scripts/review_academic_profile.py --jd data/academic_benchmark/jds/JD05.txt --output /tmp/skillbridge-review.json --temperature 0.0
.venv/bin/python scripts/chat_academic_profile.py --jd data/academic_benchmark/jds/JD05.txt --review data/academic_benchmark/initial_reviews/internship-20261013/JD05.json --temperature 0.0
```

## Phụ lục A — Tất cả findings P0/P1 còn lại

Bảng dưới giữ nguyên nội dung annotation, bao gồm cả thiếu sót ở pilot/A/B. Các file request liên kết chứa reply/evidence nguyên bản và đủ context để đối chiếu; P2 có trong annotations đầy đủ. Tên operation xác định review, chat case/lượt hoặc candidate, không coi các lỗi này là validation failures.

| Output live | Mức | Claim / CLO đối chiếu hoặc diễn giải cần sửa |
| --- | --- | --- |
| [pilot-SQL_ATTRIBUTION](../data/academic_benchmark/evaluations/internship-20261013/requests/pilot-SQL_ATTRIBUTION.json) | P1 | Sửa đúng SQL thuộc ADY201m/CLO7, DAP391m/CLO7 không nêu SQL; nhưng không cite DAP391m/CLO7 khi mô tả cụ thể scope của CLO đó. |
| [pilot-SQL_ACHIEVEMENT](../data/academic_benchmark/evaluations/internship-20261013/requests/pilot-SQL_ACHIEVEMENT.json) | P1 | So sánh DBI202/CLO5–6 basic, ADY201m/CLO1 good và CLO7 excellent nhưng thiếu exact scores 5.96, 8.3, 8.61. |
| [review-JD00](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD00.json) | P1 | Row Python mô tả PFP191/CLO1–7 gồm điều khiển/file/data structures nhưng evidence chỉ CLO1 và CLO7; thiếu CLO3/5/6 cho các ý cụ thể. |
| [review-JD00](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD00.json) | P1 | Conclusion quy giới hạn profile thành phạm vi chương trình đào tạo; hồ sơ không chứng minh toàn bộ curriculum không có công nghệ đó. |
| [chat-JD00-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD00-1.json) | P1 | Nhắc thành tích xuất sắc của nhóm CLO nhưng không nêu điểm/CLO performance rõ cho từng nhóm được hỏi. |
| [chat-JD00-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD00-2.json) | P1 | Production experience nằm chung danh sách nội dung kiến thức chưa xác nhận; claim dự án học thuật không cite project CLO. |
| [chat-JD00-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD00-2.json) | P1 | Gợi ý làm nổi bật khi ứng tuyển vượt topic clarification trong scope V1. |
| [review-JD01](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD01.json) | P0 | Row Evaluate AI algorithms/LLM/VLM nói PCA và hồi quy tuyến tính nhưng evidence chỉ CPV301/CLO8, MAI391/CLO7; thiếu MAI391/CLO6 và CLO5. Có IDs hợp lệ nhưng không hỗ trợ các phương pháp được nêu. |
| [review-JD01](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD01.json) | P1 | Các rows mô tả toàn bộ PFP191/CPV301 nhưng chỉ cite CLO subset; hàng project AIL303m/CLO10 không giải thích achievement basic, overview/conclusion thiên về good/excellent. |
| [chat-JD01-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD01-1.json) | P0 | Nêu nhận diện khuôn mặt/theo dõi đối tượng nhưng evidence CPV301/CLO3,8 không hỗ trợ; CLO9 mới mô tả hai kỹ thuật này. AIG202c ML/DL cũng không được cite. |
| [chat-JD01-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD01-1.json) | P1 | Không giải thích performance/điểm riêng khi liệt kê nhiều học phần. |
| [chat-JD01-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD01-2.json) | P0 | Nói các CLO xác nhận đã làm dự án AI/CV, trong khi refs project chỉ thể hiện intended data/ML outcomes và không nêu CV project thực tế. |
| [chat-JD01-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD01-2.json) | P1 | Backend preferred không được giữ nhãn ưu tiên; trộn knowledge với kinh nghiệm/phát triển sản phẩm và gợi ý làm nổi bật khi ứng tuyển. |
| [chat-JD01-3](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD01-3.json) | P0 | Gán nhận diện khuôn mặt/theo dõi vào CPV301/CLO8 và nâng thành hiểu/triển khai; CLO8 chỉ object detection, CLO9 Explain face recognition/tracking. |
| [review-JD02](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD02.json) | P1 | Đánh covered cho real-time detection pipeline dù CLO8 chỉ general object detection; thiếu realtime/pipeline scope. |
| [review-JD02](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD02.json) | P1 | Thêm graduation/interest như rows học thuật; tách Python/C++ mà không giữ ambiguity của dấu /. |
| [chat-JD02-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD02-1.json) | P1 | Nâng Understand/Explain/Explore AI thành nắm vững; dùng dự án thực tế thay intended academic outcomes. Không nêu kết quả CLO/điểm dù expected có performance. |
| [chat-JD02-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD02-2.json) | P1 | Không cite project CLO dù mô tả DAP391m/CLO7 và ADY201m/CLO7; giữ C++ như gap riêng trong source slash không rõ Boolean. |
| [chat-JD02-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD02-2.json) | P1 | Đưa tình trạng tốt nghiệp vào câu hỏi kiến thức và gợi ý làm nổi bật khi ứng tuyển. |
| [chat-JD02-3](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD02-3.json) | P1 | Không làm rõ YOLO do sinh viên đưa vào câu hỏi, không nằm trong JD02; cụm các framework mà JD yêu cầu dễ gộp YOLO vào source. Phân biệt CLO/framework vẫn đúng. |
| [review-JD03](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD03.json) | P0 | Row collect/clean/annotate nói DAP391m/CLO1–2 bao gồm dữ liệu hình ảnh, không có trong descriptions; broad dataset knowledge bị chuyển thành image-specific coursework. |
| [review-JD03](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD03.json) | P0 | Row training/evaluation báo excellent/good cho refs gồm AIL303m/CLO10; CLO10 thực tế 5.42/basic, không good. |
| [review-JD03](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD03.json) | P1 | Covered augmentation dù comment thừa nhận không nêu; covered research reading/C++ trong compound row dù chưa có bằng chứng; thiếu annotation coverage đúng. |
| [chat-JD03-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD03-1.json) | P0 | Gán dữ liệu hình ảnh cho DAP391m/CLO1–2; descriptions chỉ generic dataset import/clean/wrangle/EDA. |
| [chat-JD03-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD03-1.json) | P1 | Chưa trình bày achievement của từng CLO; report writing không chứng minh research-document reading. |
| [chat-JD03-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD03-2.json) | P1 | Evidence rỗng trong khi khẳng định dự án học thuật hỗ trợ integration/testing; bỏ sót annotation/augmentation cần phân biệt scope. |
| [chat-JD03-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD03-2.json) | P1 | Thêm quy trình testing chuyên sâu/hệ thống lớn không được JD yêu cầu; internship assistance không có nghĩa prior deep professional experience. |
| [review-JD04](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD04.json) | P0 | Overview/conclusion nói RAG có trong CLO ở mức tổng quan dù các CLO AIG202c không nêu RAG; row general ML nêu PCA/SVM/clustering nhưng chỉ cite AIL303m/CLO4 và MAI391/CLO5. |
| [review-JD04](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD04.json) | P0 | Gán deployment cho DAP391m/CLO7, trong khi deployment explicit ở ADY201m/CLO7, không DAP391m/CLO7. |
| [review-JD04](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD04.json) | P0 | SQL row gộp ADY201m/CLO1 và CLO7 thành khá/good; CLO7 thực tế 8.61/excellent. |
| [review-JD04](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD04.json) | P1 | Nhiều ý CV/ML/SQL không đủ evidence và bỏ sót weak bands trong tổng hợp. |
| [chat-JD04-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD04-1.json) | P0 | Nêu PCA/SVM/clustering nhưng refs chỉ AIL303m/CLO4, MAI391/CLO5; nêu agent tools nhưng AIG202c/CLO3 chỉ Explore generative models, không agent. |
| [chat-JD04-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD04-1.json) | P0 | Nói đã thực hiện API projects thay intended outcomes; face/tracking cũng thiếu CPV301/CLO9 trong evidence. |
| [chat-JD04-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD04-1.json) | P1 | SQL performance basic/good/excellent không được giải thích riêng. |
| [chat-JD04-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD04-2.json) | P0 | Gán deployment academic projects và khái niệm agent cho evidence rỗng; reuse sai scope từ history trước. |
| [chat-JD04-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD04-2.json) | P1 | ONNX preferred không được giữ rõ status; absence Git cần phân biệt GitHub tool list, không coi cùng một kỹ năng. |
| [chat-JD04-3](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD04-3.json) | P0 | Ví dụ project DAP391m/CLO7 được nói mô tả deployment trong học thuật; description không có deployment. ADY201m/CLO7 mới có từ này. |
| [review-JD05](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD05.json) | P0 | Nói không có CLO trực tiếp đề cập R trong row Python OR R dù chính ADY201m/CLO3 có R trong tool list. List dùng ít nhất một không chứng minh thực hành R, nhưng không được phủ nhận có đề cập R. |
| [review-JD05](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD05.json) | P0 | Nêu kiểm định giả thuyết/tối ưu hóa mà thiếu MAS291/CLO8, MAI391/CLO4 trong evidence; AIL303m/CLO10 basic bị gộp good/excellent. |
| [review-JD05](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD05.json) | P1 | SQL/BI preferred mất nhãn trong jd_requirement; overview/conclusion tổng quát SQL chủ yếu basic dù các CLO có bands riêng. |
| [chat-JD05-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD05-1.json) | P1 | Không nêu individual scores/bands; evidence bỏ MAS291/CLO8 dù nói kiểm định giả thuyết, PFP file/data/control còn thiếu các CLO tương ứng. |
| [chat-JD05-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD05-2.json) | P0 | Nói ADY201m/CLO7 có dashboard; description chỉ visualization, dashboard nằm DAP391m/CLO7. Phủ nhận tất cả CLO về R dù ADY201m/CLO3 liệt kê R. |
| [chat-JD05-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD05-2.json) | P1 | Python OR R biến R thành chủ đề bổ sung để đáp ứng đầy đủ; giả định prior professional product experience từ cơ hội training Sapo. |
| [chat-JD05-3](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD05-3.json) | P0 | Khẳng định chưa có học thuật về R thay vì phân biệt R được nhắc trong ADY201m/CLO3 với use-at-least-one chưa chứng minh sử dụng R. |
| [chat-JD05-3](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD05-3.json) | P1 | So sánh basic/good/excellent không trích 5.96/8.3/8.61; claim Python không cite PFP191 hoặc ADY201m Python CLO. |
| [review-JD06](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD06.json) | P0 | BI row gán Jupyter/RStudio/Watson Studio và dashboard cho DAP391m/CLO3–4, ADY201m/CLO1,7; tool list ở ADY201m/CLO3, dashboard ở DAP391m/CLO7 không được cite trong row. |
| [review-JD06](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD06.json) | P1 | Hầu hết covered/related rows không giải thích achievement, còn inferred traits attention-to-detail bị coi covered. |
| [chat-JD06-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD06-1.json) | P0 | Nói đã sử dụng Jupyter/RStudio/Watson Studio với refs không có ADY201m/CLO3; ngay cả tool list use-at-least-one cũng không xác nhận dùng mọi tool. |
| [chat-JD06-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD06-1.json) | P1 | Không nêu scores/bands; lặp nhóm trực quan hóa/dashboard hai lần. |
| [chat-JD06-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD06-2.json) | P0 | Các refs DAP391m/CLO3–4, ADY201m/CLO1,7 không ghi dashboard/Jupyter/Watson; thiếu CLO đúng cho academic claims. |
| [chat-JD06-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD06-2.json) | P1 | Gợi ý làm nổi bật ngoài trường khi ứng tuyển thay phạm vi academic topic clarification. |
| [chat-JD06-3](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD06-3.json) | P0 | Framework absence đúng, nhưng gán dashboard và Jupyter/Watson cho các CLO không nêu; câu summary lặp attribution sai của history. |
| [review-JD07](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD07.json) | P0 | Row clean/transform ghi good/excellent cho DAP391m/CLO1 và AIL303m/CLO1; cả hai thực tế good, DAP=8.45, AIL=7.56. |
| [review-JD07](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD07.json) | P1 | ADY201m/CLO4 Understand methodology bị chuyển thành Apply; conclusion riêng SQL đạt basic dù ADY201m/CLO1 good. |
| [review-JD07](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD07.json) | P1 | R bị phủ nhận thay vì tách topic trong ADY201m/CLO3 với usage chưa xác định. |
| [chat-JD07-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD07-1.json) | P0 | Nói DAP391m/CLO1 excellent; giá trị gốc 8.45/good. Đây là lỗi achievement thực tế, không chỉ vấn đề diễn đạt. |
| [chat-JD07-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD07-1.json) | P1 | So sánh nhiều bands không có scores; Understand ADY201m/CLO4 được nói đã thực hành triển khai. |
| [chat-JD07-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD07-2.json) | P1 | Đổi Python OR R preferred thành yêu cầu; kiến thức R nói chưa xác nhận không phân biệt ADY201m/CLO3 đã nhắc R nhưng không chứng minh sử dụng R. |
| [chat-JD07-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD07-2.json) | P1 | GPA/English trộn trong danh sách kiến thức thay điều kiện không thể xác minh từ CLO, và Python excellent bị gán ở cấp language. |
| [review-JD08](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD08.json) | P0 | ML row nói mọi CLO good/excellent nhưng AIL303m/CLO9=6.87/basic. |
| [review-JD08](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD08.json) | P0 | Feature engineering được gán thêm cho ADY201m/CLO7 dù description không nêu feature engineering; CLO đúng AIL303m/CLO2 có cite nhưng không làm attribution khác đúng. |
| [review-JD08](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD08.json) | P1 | A/B testing covered và conclusion gồm A/B testing dù chỉ foundation hypothesis/confidence, chưa có named A/B curriculum; project-experience covered không phải chứng minh artifact thực hiện. |
| [review-JD08](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD08.json) | P1 | Overview gọi cloud plus trong khi fixture/prerequisites liệt kê cloud experience, không source-marked optional. |
| [chat-JD08-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD08-1.json) | P1 | Nói đã triển khai các dự án, không giữ intended academic outcomes; performance chỉ một nhóm excellent, không giải thích AIL303m/CLO9 basic. |
| [chat-JD08-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD08-2.json) | P1 | Academic supervised/regression/classification claims trong đoạn recommender không có evidence ở response này; evidence rỗng dù mô tả nền tảng đã học. |
| [review-JD09](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD09.json) | P0 | Row data structures gán sorting/graphs cho CSD203/CLO1–4; đúng sorting=CLO6, graph=CLO5. Refs chỉ CSD203/CLO1 và MAD101/CLO7, không hỗ trợ stack/tree/Prim/Kruskal đã nêu. |
| [review-JD09](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD09.json) | P1 | Covered compound ML row dù ensembles/cross-validation không nêu; language OR được quyết định any trong source grouping chưa rõ; phủ nhận Scala dù ADY201m/CLO3 có topic Scala (usage không chắc). |
| [review-JD09](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD09.json) | P1 | Conclusion gọi completed academic projects và xuất sắc SQL/DSA, trong khi DBI202 basic và CSD203 CLO5–8 basic; grades bị khái quát. |
| [chat-JD09-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD09-1.json) | P0 | Nêu graph/Dijkstra/Prim/Kruskal/SVM nhưng refs chỉ CSD203/CLO1, MAD101/CLO7, MAI391/CLO6; thiếu CSD203/CLO5 và MAI391/CLO7 cho named methods. |
| [chat-JD09-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD09-1.json) | P1 | Actual completed project wording, thiếu scores/bands và SQL curriculum bị gọi cơ bản từ achievement. |
| [chat-JD09-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD09-2.json) | P1 | Source employer stack và preferred Spark không được phân biệt rõ với mandatory topics trong gap conclusion; Scala topic được phủ nhận dù tool-list ADY201m/CLO3 nêu, không chứng minh usage nhưng không phải không nhắc. |
| [chat-JD09-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD09-2.json) | P1 | Production responsibilities bị trình bày như prior experience requirement; added Hadoop ngoài tên JD chỉ là ví dụ không academic fact. |
| [review-JD10](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD10.json) | P0 | Covered pandas/numpy và claim JSON/CSV được gán ADY201m/DAP391m CLOs; canonical descriptions không nêu các tên này. |
| [review-JD10](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD10.json) | P1 | SQL curriculum bị nói chủ yếu cơ bản từ basic achievement; MCP được giải thích sai Multi-Channel Platform thay Model Context Protocol. |
| [review-JD10](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD10.json) | P1 | Có nhãn preferred cho nhóm RAG/MCP, nhưng thêm gaming-interest vào review học thuật không có nguồn đánh giá. |
| [chat-JD10-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD10-1.json) | P0 | Khẳng định đã sử dụng pandas/numpy và JSON/CSV qua ADY201m/CLO5,7/DAP391m; chỉ có Python libraries/API tổng quát trong description. |
| [chat-JD10-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD10-1.json) | P1 | Trình bày đã xây dựng/triển khai workflows AI thực tế thay learning outcomes; không nêu CLO scores/bands. |
| [chat-JD10-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD10-2.json) | P1 | MCP expansion sai; SQL CLOs bị gọi chỉ mức cơ bản do basic label; RAG/BigQuery/Snowflake nice-to-have không được giữ status trong danh sách gap. |
| [chat-JD10-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD10-2.json) | P1 | Mô tả AIG202c/CLO4 prompt curriculum nhưng evidence rỗng. |
| [chat-JD10-3](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD10-3.json) | P1 | MCP được gọi Multi-Channel Platform, sai nghĩa Model Context Protocol trong JD agent/tool-calling. Academic absence/structured output distinction đúng. |
| [review-JD11](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD11.json) | P0 | Gán API integration cho ADY201m/CLO7/DAP391m/CLO7; hai description không có API, CLO đúng ADY201m/CLO5 và DAP391m/CLO5–6. |
| [review-JD11](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD11.json) | P0 | Conclusion nói các CLO đều tốt/xuất sắc trong khi SQL DBI202/CLO5–6 =5.96/basic. |
| [review-JD11](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD11.json) | P1 | Databases OR similar chưa nhận SQL Server là RDBMS tương tự; curriculum và performance không tách rõ, thiếu exact scores. |
| [chat-JD11-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD11-1.json) | P1 | Claim cấu trúc dữ liệu/CSD203/CSI106 không cite CLO; công việc Watson được nói đã triển khai thay intended outcomes; thiếu grades. |
| [chat-JD11-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD11-1.json) | P1 | ADY201m/CLO7/DAP391m/CLO7 không nêu API dù phần workflow gộp chúng với các CLO API có thật. |
| [chat-JD11-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD11-2.json) | P1 | Không phân biệt cloud/queues/API principles preferred và SQL Server có thể đáp ứng OR similar; gợi ý bổ sung toàn bộ như đầy đủ yêu cầu. |
| [chat-JD11-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD11-2.json) | P1 | Positive claim đã thao tác API nhưng evidence rỗng; DAP/ADY API CLO phải được cite khi khẳng định. |
| [review-JD12](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD12.json) | P0 | Conclusion khẳng định sử dụng GitHub mặc dù ADY201m/CLO3 chỉ yêu cầu biết danh sách và dùng ít nhất một tool; chưa chứng minh dùng GitHub. |
| [review-JD12](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD12.json) | P1 | Gộp Python AND Git thành covered trong khi comment thừa nhận Git chưa xác nhận; không giữ rõ SQL/orchestration/cloud/Docker là nice-to-have. Nhiều comment kể CLO ngoài evidence. |
| [chat-JD12-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD12-1.json) | P1 | Một số claims về PFP191/CLO1–7 và DAP391m rộng hơn các references được chọn; so sánh achievement chưa ghi điểm từng CLO. |
| [chat-JD12-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD12-2.json) | P1 | Claim học thuật về Cloud AIL303m/CLO1 và tools ADY201m/CLO3 không có evidence; chưa phân biệt nice-to-have. Công nghệ và trải nghiệm thực tế được liệt kê chung. |
| [chat-JD12-3](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD12-3.json) | P0 | Summary nói môn dự án dữ liệu DAP391m/CLO7 đáp ứng tốt yêu cầu SQL, trong khi description CLO7 không nêu SQL/database access; evidence chỉ CLO này. |
| [chat-JD12-3](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD12-3.json) | P1 | Bịa trích dẫn Required ... SQL and basic data modeling; fixture Jua đặt SQL ở Nice-to-have. |
| [review-JD13](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD13.json) | P1 | Thêm row Final-year IT study mà các CLO không xác nhận năm học; related chỉ là foundation, cần giữ rõ chưa xác minh điều kiện hành chính. |
| [chat-JD13-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD13-1.json) | P1 | Một số nội dung Python toàn môn được kể với references giới hạn; bands thành tích không kèm điểm, không nên suy mức chung. |
| [chat-JD13-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD13-2.json) | P1 | Claim đã học hệ điều hành/mạng thiếu references (evidence rỗng). Cụm làm nổi bật khi ứng tuyển lệch khỏi giải thích học thuật. |
| [review-JD14](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD14.json) | P1 | Degree/study covered dựa vào CLO không xác minh văn bằng/năm học; row AI/project và Python kể scope rộng hơn evidence. Preferred kỹ thuật được giữ riêng. |
| [chat-JD14-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD14-1.json) | P0 | Cụm hiểu và triển khai ... nhận diện khuôn mặt nâng CPV301/CLO9 từ Explain lên triển khai; ITE303c được gộp thành công cụ/triển khai AI trong khi nội dung chính là ethics/fairness/privacy. |
| [chat-JD14-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD14-1.json) | P1 | Kể phạm vi Python và hệ thống toàn môn với evidence rút gọn; nhiều nhóm xa requirements robotics. |
| [chat-JD14-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD14-2.json) | P1 | Gộp C++/ROS, kinh nghiệm công nghiệp và advanced degree vào danh sách chủ đề có thể bổ sung/làm nổi bật; chưa tách kiến thức với kinh nghiệm và điều kiện bằng cấp. |
| [chat-JD14-3](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD14-3.json) | P1 | PFP191/CLO1–7 được nói gồm data structures nhưng evidence chỉ CLO1/7; không có CLO6. |
| [chat-JD02-4](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD02-4.json) | P1 | Nâng CPV301/CLO4 từ Understand feature extraction/matching + Implement edge/line extraction thành implement mọi feature extraction; kết luận đã học đầy đủ object detection rộng hơn scope CLO. |
| [chat-JD02-5](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD02-5.json) | P1 | Summary giữ claim phạm vi feature extraction rộng từ lượt trước, không nêu 8.81/excellent khi tổng kết CLO8. Nhiều môn/CLO bổ sung rộng mà summary ít phân biệt scope. |
| [chat-JD05-4](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD05-4.json) | P1 | Achievement từng CLO basic được phân biệt đúng với curriculum, nhưng thiếu điểm 5.96 khi diễn giải thành tích. |
| [chat-JD05-5](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD05-5.json) | P0 | Gán tối ưu hóa cho MAI391/CLO3/5/6/7; continuous optimization thuộc CLO4. Summary có references PCA/SVM đúng nhưng thiếu đúng CLO cho claim mới optimization. |
| [chat-JD05-5](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD05-5.json) | P1 | Các claim MAS291/CLO1–9 và DAP391m/CLO1–7 rộng hơn evidence; achievement không kèm điểm. |
| [chat-JD11-4](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD11-4.json) | P0 | Gán API cho ADY201m/CLO7 và DAP391m/CLO7 dù descriptions hai CLO không nêu API. ADY201m/CLO5 và DAP391m/CLO5/6 mới hỗ trợ API. |
| [chat-JD11-5](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD11-5.json) | P1 | Summary gộp DAP391m/CLO5/6/7 và ADY201m/CLO1/5/7 như nhóm API mà không sửa attribution sai CLO7 từ lượt trước. Claim API nói chung có CLO5/6 hỗ trợ, nên không chấm P0 cho riêng aggregate này. |
| [temperature-JD02-0_3](../data/academic_benchmark/evaluations/internship-20261013/requests/temperature-JD02-0_3.json) | P1 | Giữ ambiguity YOLO do người hỏi đưa vào nhưng không có trong JD02; framework/công nghệ JD yêu cầu dễ hiểu bao gồm YOLO. |
| [temperature-JD05-0_3](../data/academic_benchmark/evaluations/internship-20261013/requests/temperature-JD05-0_3.json) | P1 | Kết luận đã đáp ứng đủ yêu cầu chính của JD chỉ từ Python/SQL rộng hơn đối chiếu học thuật có giới hạn; thiếu reference Python và exact CLO scores. |
| [temperature-JD10-0_3](../data/academic_benchmark/evaluations/internship-20261013/requests/temperature-JD10-0_3.json) | P1 | Lặp nghĩa sai MCP = Multi-Channel Platform từ history; nghĩa đúng là Model Context Protocol. |

## Phụ lục B — Reply A/B nguyên bản

Các reply dưới đây được chép nguyên chuỗi từ `structured_output.reply`; chỉ thêm ký hiệu blockquote để hiển thị. Không chỉnh câu sai. Evidence và chín scores nằm tại liên kết trace/annotations; các tên công nghệ/claim sai trong trích dẫn là kết quả model, không phải xác nhận của báo cáo.

### JD02 — FPT Software

**Temperature 0.0** — [chat-JD02-3](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD02-3.json)

> Bạn đã học về Object Detection trong CPV301/CLO8, với yêu cầu "hiểu và triển khai các kỹ thuật nhận diện đối tượng". Tuy nhiên, CLO này chỉ xác nhận bạn đã học các kỹ thuật nhận diện đối tượng ở mức tổng quát, không nêu cụ thể framework, thư viện hay công nghệ nào như YOLO hoặc PyTorch.
> 
> Để một công nghệ cụ thể như YOLO hoặc PyTorch được xác nhận trong hồ sơ học thuật, cần có CLO hoặc mô tả môn học ghi rõ tên công nghệ đó. Trong hồ sơ hiện tại, không có CLO nào đề cập trực tiếp đến YOLO, PyTorch, ONNX, TensorRT hay OpenCV. Vì vậy, dù bạn đã học về lý thuyết và kỹ thuật nhận diện đối tượng, hồ sơ chỉ xác nhận phạm vi tổng quát, chưa xác nhận thực hành hoặc kiến thức về các framework/công nghệ cụ thể mà JD yêu cầu.
> 
> Nếu bạn đã tự học hoặc thực hành với YOLO, PyTorch ngoài chương trình học, hồ sơ này chưa phản ánh được điều đó.

Evidence: `CPV301/CLO8`.

**Temperature 0.3** — [temperature-JD02-0_3](../data/academic_benchmark/evaluations/internship-20261013/requests/temperature-JD02-0_3.json)

> Bạn đã học về Object Detection thông qua CLO CPV301/CLO8, trong đó yêu cầu hiểu và triển khai các kỹ thuật nhận diện đối tượng. Tuy nhiên, CLO này chỉ mô tả ở mức tổng quát về object detection, không chỉ rõ framework, thư viện hay công nghệ cụ thể nào như YOLO hoặc PyTorch.
> 
> Để một công nghệ cụ thể như YOLO hoặc PyTorch được xác nhận trong hồ sơ học thuật, cần có CLO nêu rõ việc học, sử dụng hoặc thực hành với chính công nghệ đó. Trong hồ sơ hiện tại, các CLO liên quan đến AI, Computer Vision, học máy và lập trình Python đều không đề cập trực tiếp đến YOLO, PyTorch, ONNX, TensorRT hay OpenCV. Vì vậy, dù bạn đã học về object detection, hồ sơ chỉ xác nhận kiến thức nền tảng và phương pháp chung, chưa xác nhận từng framework/công nghệ cụ thể mà JD yêu cầu.
> 
> Nếu bạn đã tự học hoặc thực hành với YOLO, PyTorch ngoài chương trình học, hồ sơ này chưa phản ánh được điều đó.

Evidence: `CPV301/CLO8`.


### JD05 — Sapo

**Temperature 0.0** — [chat-JD05-3](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD05-3.json)

> Về SQL, không thể gán một mức tổng thể cho kỹ năng SQL của bạn chỉ dựa trên một nhãn "basic". Trong hồ sơ, các CLO về SQL ở DBI202 (CLO5, CLO6, CLO7) đều có thành tích "basic", nghĩa là bạn đã được đánh giá ở mức cơ bản về các chủ đề như DDL, DML, T-SQL, stored procedures, triggers, transaction và tối ưu hóa truy vấn trên Microsoft SQL Server. Tuy nhiên, ADY201m (CLO1, CLO7) lại có thành tích "good" và "excellent" về thực hành truy cập cơ sở dữ liệu bằng SQL trong bối cảnh dự án khoa học dữ liệu. Như vậy, các CLO này phản ánh thành tích riêng biệt ở từng nội dung, không xác nhận một mức tổng thể duy nhất cho kỹ năng SQL của bạn.
> 
> Về yêu cầu của JD, JD chỉ yêu cầu sử dụng Python hoặc R cho phân tích dữ liệu (không bắt buộc cả hai). SQL là tiêu chí ưu tiên (preferred), không phải bắt buộc tuyệt đối. Bạn đã có bằng chứng học thuật về Python và SQL, nhưng chưa có về R.

Evidence: `DBI202/CLO5`, `DBI202/CLO6`, `DBI202/CLO7`, `ADY201m/CLO1`, `ADY201m/CLO7`.

**Temperature 0.3** — [temperature-JD05-0_3](../data/academic_benchmark/evaluations/internship-20261013/requests/temperature-JD05-0_3.json)

> Về SQL: Không thể gán một mức SQL tổng thể từ các nhãn CLO này, vì mỗi CLO phản ánh một nội dung và thành tích riêng biệt. Ở môn DBI202, các CLO về SQL (CLO5: sử dụng DDL/DML, CLO6: T-SQL, stored procedures, triggers, transaction, CLO7: chỉ mục, tối ưu hóa truy vấn) đều có thành tích "basic". Tuy nhiên, ADY201m (CLO1: kiến thức SQL nền tảng, CLO7: thực hành truy cập cơ sở dữ liệu bằng SQL trong dự án khoa học dữ liệu) lại đạt "good" và "excellent". Như vậy, bạn có bằng chứng học thuật về cả lý thuyết lẫn thực hành SQL, với mức độ đạt được khác nhau tùy CLO, không phải chỉ ở mức basic cho toàn bộ kỹ năng SQL.
> 
> Về yêu cầu của JD: JD chỉ yêu cầu sử dụng Python hoặc R cho phân tích dữ liệu, không bắt buộc phải biết cả hai. SQL là tiêu chí ưu tiên (preferred), không phải điều kiện bắt buộc. Vì vậy, bạn đã có nền tảng Python và bằng chứng về SQL là đã đáp ứng đủ yêu cầu chính của JD này.

Evidence: `DBI202/CLO5`, `DBI202/CLO6`, `DBI202/CLO7`, `ADY201m/CLO1`, `ADY201m/CLO7`.


### JD09 — Poshmark

**Temperature 0.0** — [chat-JD09-3](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD09-3.json)

> Nếu bạn nói đã học PCA, SVM và hồi quy thì có thể dựa vào các CLO sau:
> 
> - Hồi quy (Linear Regression): MAI391/CLO5 xác nhận bạn đã học về hồi quy tuyến tính, các phương pháp ước lượng tham số, overfitting, Bayesian linear regression.
> - PCA (Principal Component Analysis): MAI391/CLO6 xác nhận bạn đã học về giảm chiều dữ liệu với PCA, bao gồm các khái niệm về ma trận hiệp phương sai, không gian con chính, xấp xỉ ma trận hạng thấp, và các bước thực hành PCA.
> - SVM (Support Vector Machine): MAI391/CLO7 xác nhận bạn đã học về phân loại bằng SVM, bao gồm hyperplane, SVM tuyến tính và kernel, các phương pháp giải số để tìm nghiệm tối ưu.
> 
> Việc các CLO này xác nhận bạn đã học PCA, SVM và hồi quy không đồng nghĩa với việc bạn đã sử dụng PyTorch. Các CLO trên chỉ mô tả về lý thuyết, thuật toán và ứng dụng các phương pháp này, không đề cập đến việc triển khai bằng PyTorch hay bất kỳ deep learning framework cụ thể nào. Nếu JD yêu cầu kinh nghiệm với PyTorch, bạn cần có bằng chứng học thuật hoặc dự án cụ thể về việc sử dụng framework này.

Evidence: `MAI391/CLO5`, `MAI391/CLO6`, `MAI391/CLO7`.

**Temperature 0.3** — [temperature-JD09-0_3](../data/academic_benchmark/evaluations/internship-20261013/requests/temperature-JD09-0_3.json)

> Nếu bạn nói đã học PCA, SVM và hồi quy thì có thể dựa vào các CLO sau:
> 
> - PCA: MAI391/CLO6 xác nhận bạn đã học về giảm chiều dữ liệu với PCA, bao gồm các khái niệm như ma trận hiệp phương sai, không gian con chính, xấp xỉ ma trận hạng thấp, tính toán eigenvector và các bước thực hành PCA.
> - SVM: MAI391/CLO7 xác nhận bạn đã học về phân loại bằng Support Vector Machine, bao gồm hyperplane phân tách, SVM dạng nguyên thủy và đối ngẫu, kernel cho phân loại phi tuyến và các phương pháp số để tìm nghiệm tối ưu.
> - Hồi quy: MAI391/CLO5 xác nhận bạn đã học về hồi quy tuyến tính, ước lượng tham số, maximum likelihood, maximum a posteriori, lỗi khái quát hóa, overfitting và Bayesian linear regression. Ngoài ra, AIL303m/CLO4 cũng đề cập đến hồi quy tuyến tính trong supervised learning.
> 
> Việc học PCA, SVM và hồi quy theo các CLO này xác nhận bạn đã học lý thuyết và áp dụng các phương pháp này trong bối cảnh toán học và học máy. Tuy nhiên, các CLO này không xác nhận bạn đã sử dụng PyTorch hay bất kỳ deep learning framework cụ thể nào. Để xác nhận đã dùng PyTorch, cần có CLO nêu rõ việc thực hành hoặc triển khai bằng PyTorch (hoặc framework tương tự), nhưng hồ sơ hiện tại chưa có bằng chứng này.

Evidence: `MAI391/CLO6`, `MAI391/CLO7`, `MAI391/CLO5`, `AIL303m/CLO4`.


### JD10 — VNGGames

**Temperature 0.0** — [chat-JD10-3](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD10-3.json)

> Bạn đã có bằng chứng học thuật về prompt engineering thông qua AIG202c (CLO4), trong đó đề cập đến các kỹ thuật và công cụ xây dựng prompt cho Generative AI. Tuy nhiên:
> 
> - Structured Outputs (ví dụ: xuất dữ liệu có cấu trúc như JSON/XML từ LLM): CLO này chỉ xác nhận bạn đã học về kỹ thuật xây dựng prompt, chưa xác nhận rõ ràng về thực hành xuất dữ liệu có cấu trúc từ LLM hoặc workflow áp dụng structured output.
> 
> - RAG (Retrieval-Augmented Generation) và MCP (Multi-Channel Platform): Không có CLO nào trong hồ sơ học thuật xác nhận bạn đã học hoặc thực hành về RAG, vector search, hay MCP. Đây là các công nghệ chuyên biệt mà JD nêu rõ, nhưng hồ sơ hiện tại chưa có bằng chứng học thuật về chúng.
> 
> Tóm lại, bạn có bằng chứng về kiến thức prompt engineering, nhưng chưa có bằng chứng học thuật về structured outputs từ LLM, RAG hoặc MCP.

Evidence: `AIG202c/CLO4`.

**Temperature 0.3** — [temperature-JD10-0_3](../data/academic_benchmark/evaluations/internship-20261013/requests/temperature-JD10-0_3.json)

> Bạn đã có bằng chứng học thuật về prompt engineering thông qua AIG202c (CLO4), trong đó đề cập đến các kỹ thuật và công cụ xây dựng prompt cho Generative AI. Tuy nhiên, CLO này chỉ xác nhận kiến thức về kỹ thuật xây dựng prompt và prompt engineering cơ bản, chưa xác nhận rõ về thực hành xuất dữ liệu có cấu trúc (structured outputs như JSON/XML), cũng như chưa đề cập đến các workflow áp dụng structured output từ LLM.
> 
> Ngoài ra, hồ sơ hiện tại không có CLO nào xác nhận bạn đã học hoặc thực hành về RAG (Retrieval-Augmented Generation) hoặc MCP (Multi-Channel Platform). Đây là các công nghệ và framework chuyên biệt, không nằm trong phạm vi các CLO về prompt engineering hoặc AI/ML tổng quát đã được học.
> 
> Tóm lại:
> - Prompt engineering: Có bằng chứng học thuật (AIG202c/CLO4).
> - Structured outputs (JSON/XML từ LLM): Chưa có CLO xác nhận rõ.
> - RAG, MCP: Chưa có CLO nào xác nhận đã học hoặc thực hành các nội dung này.

Evidence: `AIG202c/CLO4`.


### JD11 — Tessera Labs

**Temperature 0.0** — [chat-JD11-3](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD11-3.json)

> Bạn đã học Python (bao gồm lập trình hướng đối tượng, thao tác với API, xử lý dữ liệu) và SQL (DDL, DML, T-SQL trên Microsoft SQL Server) qua các CLO như PFP191/CLO7, DBI202/CLO5, DBI202/CLO6, ADY201m/CLO1, CLO5, CLO7. Tuy nhiên, các công nghệ như FastAPI, SQLAlchemy và PostgreSQL là những framework, thư viện hoặc hệ quản trị cơ sở dữ liệu cụ thể, đòi hỏi nội dung học thuật phải nêu rõ tên hoặc phạm vi sử dụng chúng.
> 
> - FastAPI và SQLAlchemy là các framework/thư viện Python chuyên biệt để xây dựng REST API và thao tác ORM với cơ sở dữ liệu. Hồ sơ của bạn xác nhận nền tảng Python, OOP và thao tác với API, nhưng không có CLO nào đề cập trực tiếp đến việc học hoặc thực hành với FastAPI hay SQLAlchemy.
> - PostgreSQL là một hệ quản trị cơ sở dữ liệu quan hệ phổ biến. Hồ sơ xác nhận bạn đã học và thực hành với Microsoft SQL Server (DBI202), nhưng không có CLO nào xác nhận bạn đã học hoặc thao tác với PostgreSQL.
> 
> Vì vậy, dù bạn đã có nền tảng Python và SQL, hồ sơ học thuật chỉ xác nhận những công nghệ hoặc công cụ được nêu rõ trong CLO. Nếu CLO không đề cập trực tiếp đến FastAPI, SQLAlchemy hoặc PostgreSQL, thì hồ sơ không thể xác nhận bạn đã học các công nghệ này, dù chúng có liên quan về mặt kiến thức nền tảng.

Evidence: `PFP191/CLO7`, `DBI202/CLO5`, `DBI202/CLO6`, `ADY201m/CLO1`, `ADY201m/CLO5`, `ADY201m/CLO7`.

**Temperature 0.3** — [temperature-JD11-0_3](../data/academic_benchmark/evaluations/internship-20261013/requests/temperature-JD11-0_3.json)

> Việc bạn đã học Python và SQL là nền tảng rất quan trọng, nhưng các công nghệ như FastAPI, SQLAlchemy hay PostgreSQL chỉ được xác nhận trong hồ sơ học thuật khi có CLO (Course Learning Outcome) đề cập trực tiếp đến chúng. 
> 
> - Python và SQL là các ngôn ngữ/công cụ nền tảng, được xác nhận qua các CLO như PFP191/CLO7 (lập trình hướng đối tượng với Python), DBI202/CLO5, CLO6 (SQL, T-SQL trên Microsoft SQL Server), và ADY201m/CLO1, CLO5, CLO7 (sử dụng Python và SQL trong workflow data science).
> 
> - Tuy nhiên, FastAPI và SQLAlchemy là các framework/thư viện chuyên biệt để xây dựng REST API và thao tác ORM trong Python, còn PostgreSQL là một hệ quản trị cơ sở dữ liệu cụ thể. Các CLO hiện tại chỉ xác nhận bạn đã học Python nói chung và SQL trên Microsoft SQL Server, chưa có CLO nào ghi rõ bạn đã học hoặc thực hành với FastAPI, SQLAlchemy hay PostgreSQL.
> 
> Do đó, dù bạn đã có nền tảng Python và SQL, hồ sơ học thuật chỉ xác nhận các công nghệ cụ thể nếu chúng được nêu rõ trong nội dung CLO.

Evidence: `PFP191/CLO7`, `DBI202/CLO5`, `DBI202/CLO6`, `ADY201m/CLO1`, `ADY201m/CLO5`, `ADY201m/CLO7`.


### JD13 — VSEC

**Temperature 0.0** — [chat-JD13-3](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD13-3.json)

> Bạn đã học hệ điều hành (CSI106/CLO5, CEA201/CLO5), mạng máy tính (CSI106/CLO4) và lập trình Python (PFP191/CLO1-7), đây là các nền tảng quan trọng để tiếp cận lĩnh vực SOC và các hệ thống SIEM/SOAR. Tuy nhiên, không thể kết luận bạn đã biết hoặc đã thực hành với SIEM, SOAR hay vận hành SOC chỉ dựa trên các học phần này.
> 
> Lý do là các CLO liên quan chỉ xác nhận bạn đã học về nguyên lý hệ điều hành, tổng quan mạng, và lập trình Python, chứ không đề cập đến nội dung cụ thể về vận hành SOC, sử dụng SIEM/SOAR, hoặc các kỹ năng thực hành giám sát an ninh mạng. Những hệ thống này thường yêu cầu kiến thức và kỹ năng chuyên biệt, không nằm trong phạm vi các CLO đã học.
> 
> Tóm lại, hồ sơ học thuật của bạn thể hiện nền tảng phù hợp để học tiếp hoặc làm quen với SOC/SIEM/SOAR, nhưng chưa xác nhận bạn đã biết hoặc đã thực hành các nội dung này.

Evidence: `CSI106/CLO5`, `CEA201/CLO5`, `CSI106/CLO4`, `PFP191/CLO1`, `PFP191/CLO2`, `PFP191/CLO3`, `PFP191/CLO4`, `PFP191/CLO5`, `PFP191/CLO6`, `PFP191/CLO7`.

**Temperature 0.3** — [temperature-JD13-0_3](../data/academic_benchmark/evaluations/internship-20261013/requests/temperature-JD13-0_3.json)

> Bạn đã học về hệ điều hành (CSI106/CLO5, CEA201/CLO5), mạng máy tính (CSI106/CLO4), và lập trình Python (PFP191/CLO1-7). Tuy nhiên, các CLO này chỉ xác nhận bạn có kiến thức nền tảng về các chủ đề đó, như vai trò và thành phần hệ điều hành, tổng quan về mạng, và kỹ năng lập trình Python.
> 
> Không có CLO nào trong hồ sơ xác nhận bạn đã học hoặc thực hành về SIEM, SOAR, hay vận hành SOC. Các hệ thống này là các công cụ và quy trình chuyên biệt trong lĩnh vực an ninh mạng, yêu cầu kiến thức và kỹ năng riêng biệt mà các CLO về hệ điều hành, mạng và lập trình Python không trực tiếp đề cập hay đánh giá. Vì vậy, không thể kết luận bạn đã biết về SIEM/SOAR hay làm SOC chỉ dựa trên các học phần này.
> 
> Nếu bạn đã tự học hoặc có kinh nghiệm thực tế về các công cụ này ngoài chương trình đại học, hồ sơ học thuật hiện tại chưa xác nhận được điều đó.

Evidence: `CSI106/CLO5`, `CEA201/CLO5`, `CSI106/CLO4`, `PFP191/CLO1`, `PFP191/CLO2`, `PFP191/CLO3`, `PFP191/CLO4`, `PFP191/CLO5`, `PFP191/CLO6`, `PFP191/CLO7`.

## Phụ lục C — Chín điểm cho từng output đã đọc

Thứ tự: JD = JD Coverage; Ground = Evidence Grounding; Ach = Academic Achievement; Gap = Gap Calibration; Exp = Knowledge vs Experience; Hist = Conversational Continuity; Full = Completeness; Nat = Naturalness; Scope = Scope Adherence. N/A không đưa vào tính đạt/không đạt.

| Output | JD | Ground | Ach | Gap | Exp | Hist | Full | Nat | Scope |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| [pilot-SQL_ATTRIBUTION](../data/academic_benchmark/evaluations/internship-20261013/requests/pilot-SQL_ATTRIBUTION.json) | N/A | 1 | N/A | 2 | 2 | 2 | 2 | 2 | 2 |
| [pilot-CV_METHODS](../data/academic_benchmark/evaluations/internship-20261013/requests/pilot-CV_METHODS.json) | N/A | 2 | N/A | 2 | 2 | 2 | 2 | 2 | 2 |
| [pilot-SQL_ACHIEVEMENT](../data/academic_benchmark/evaluations/internship-20261013/requests/pilot-SQL_ACHIEVEMENT.json) | N/A | 2 | 1 | 2 | 2 | N/A | 2 | 1 | 2 |
| [pilot-CV_FRAMEWORKS](../data/academic_benchmark/evaluations/internship-20261013/requests/pilot-CV_FRAMEWORKS.json) | 2 | 2 | N/A | 2 | 2 | N/A | 2 | 1 | 2 |
| [review-JD00](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD00.json) | 2 | 1 | 2 | 1 | 2 | N/A | 2 | 1 | 2 |
| [chat-JD00-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD00-1.json) | 2 | 2 | 1 | 2 | 2 | N/A | 2 | 1 | 2 |
| [chat-JD00-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD00-2.json) | 2 | 1 | N/A | 2 | 1 | 2 | 2 | 1 | 1 |
| [chat-JD00-3](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD00-3.json) | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 |
| [review-JD01](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD01.json) | 2 | 0 | 1 | 2 | 2 | N/A | 2 | 1 | 2 |
| [chat-JD01-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD01-1.json) | 2 | 0 | 1 | 2 | 2 | N/A | 2 | 1 | 2 |
| [chat-JD01-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD01-2.json) | 2 | 0 | N/A | 2 | 1 | 2 | 2 | 1 | 1 |
| [chat-JD01-3](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD01-3.json) | 2 | 0 | N/A | 2 | 2 | 2 | 2 | 2 | 2 |
| [review-JD02](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD02.json) | 2 | 1 | 1 | 1 | 2 | N/A | 2 | 1 | 2 |
| [chat-JD02-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD02-1.json) | 2 | 1 | 1 | 2 | 1 | N/A | 2 | 1 | 2 |
| [chat-JD02-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD02-2.json) | 1 | 1 | N/A | 1 | 2 | 2 | 1 | 1 | 1 |
| [chat-JD02-3](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD02-3.json) | 1 | 2 | N/A | 2 | 2 | 2 | 2 | 2 | 2 |
| [review-JD03](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD03.json) | 2 | 0 | 0 | 1 | 2 | N/A | 2 | 1 | 2 |
| [chat-JD03-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD03-1.json) | 2 | 0 | 1 | 2 | 2 | N/A | 2 | 1 | 2 |
| [chat-JD03-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD03-2.json) | 1 | 1 | N/A | 2 | 1 | 2 | 1 | 2 | 2 |
| [chat-JD03-3](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD03-3.json) | 2 | 2 | N/A | 2 | 2 | 2 | 2 | 2 | 2 |
| [review-JD04](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD04.json) | 2 | 0 | 0 | 1 | 1 | N/A | 2 | 1 | 2 |
| [chat-JD04-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD04-1.json) | 2 | 0 | 1 | 2 | 1 | N/A | 2 | 1 | 2 |
| [chat-JD04-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD04-2.json) | 2 | 0 | N/A | 1 | 1 | 2 | 2 | 1 | 2 |
| [chat-JD04-3](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD04-3.json) | 2 | 0 | 2 | 2 | 2 | 2 | 2 | 1 | 2 |
| [review-JD05](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD05.json) | 2 | 0 | 1 | 1 | 2 | N/A | 2 | 1 | 2 |
| [chat-JD05-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD05-1.json) | 2 | 1 | 1 | 2 | 2 | N/A | 2 | 1 | 2 |
| [chat-JD05-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD05-2.json) | 1 | 0 | N/A | 1 | 1 | 2 | 1 | 1 | 2 |
| [chat-JD05-3](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD05-3.json) | 2 | 0 | 1 | 2 | 2 | 2 | 2 | 2 | 2 |
| [review-JD06](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD06.json) | 2 | 0 | 1 | 2 | 2 | N/A | 2 | 1 | 2 |
| [chat-JD06-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD06-1.json) | 2 | 0 | 1 | 2 | 2 | N/A | 2 | 1 | 2 |
| [chat-JD06-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD06-2.json) | 2 | 0 | N/A | 2 | 1 | 2 | 2 | 1 | 1 |
| [chat-JD06-3](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD06-3.json) | 2 | 0 | N/A | 2 | 2 | 2 | 2 | 2 | 2 |
| [review-JD07](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD07.json) | 2 | 0 | 0 | 1 | 2 | N/A | 2 | 1 | 2 |
| [chat-JD07-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD07-1.json) | 2 | 1 | 0 | 2 | 2 | N/A | 2 | 1 | 2 |
| [chat-JD07-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD07-2.json) | 1 | 1 | 1 | 1 | 2 | 2 | 1 | 1 | 2 |
| [chat-JD07-3](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD07-3.json) | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 | 2 |
| [review-JD08](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD08.json) | 1 | 0 | 0 | 1 | 1 | N/A | 2 | 1 | 2 |
| [chat-JD08-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD08-1.json) | 2 | 1 | 1 | 2 | 1 | N/A | 2 | 1 | 2 |
| [chat-JD08-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD08-2.json) | 2 | 1 | N/A | 2 | 2 | 2 | 2 | 2 | 2 |
| [chat-JD08-3](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD08-3.json) | 2 | 2 | N/A | 2 | 2 | 2 | 2 | 1 | 2 |
| [review-JD09](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD09.json) | 2 | 0 | 1 | 1 | 1 | N/A | 2 | 1 | 2 |
| [chat-JD09-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD09-1.json) | 2 | 0 | 1 | 2 | 1 | N/A | 2 | 1 | 2 |
| [chat-JD09-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD09-2.json) | 1 | 1 | N/A | 1 | 1 | 2 | 2 | 1 | 2 |
| [chat-JD09-3](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD09-3.json) | 2 | 2 | N/A | 2 | 2 | 2 | 2 | 2 | 2 |
| [review-JD10](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD10.json) | 2 | 0 | 1 | 1 | 2 | N/A | 2 | 1 | 2 |
| [chat-JD10-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD10-1.json) | 2 | 0 | 1 | 2 | 1 | N/A | 2 | 1 | 2 |
| [chat-JD10-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD10-2.json) | 2 | 1 | 1 | 1 | 2 | 2 | 2 | 1 | 2 |
| [chat-JD10-3](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD10-3.json) | 2 | 1 | N/A | 2 | 2 | 2 | 2 | 2 | 2 |
| [review-JD11](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD11.json) | 2 | 0 | 0 | 1 | 1 | N/A | 2 | 1 | 2 |
| [chat-JD11-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD11-1.json) | 2 | 1 | 1 | 2 | 1 | N/A | 2 | 1 | 2 |
| [chat-JD11-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD11-2.json) | 1 | 1 | N/A | 1 | 2 | 2 | 2 | 2 | 2 |
| [chat-JD11-3](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD11-3.json) | 2 | 2 | N/A | 2 | 2 | 2 | 2 | 2 | 2 |
| [review-JD12](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD12.json) | 1 | 0 | 1 | 2 | 2 | N/A | 2 | 1 | 2 |
| [chat-JD12-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD12-1.json) | 2 | 1 | 1 | 2 | 2 | N/A | 2 | 1 | 2 |
| [chat-JD12-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD12-2.json) | 1 | 1 | N/A | 2 | 1 | 2 | 2 | 1 | 2 |
| [chat-JD12-3](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD12-3.json) | 0 | 0 | N/A | 2 | 2 | 1 | 1 | 1 | 2 |
| [review-JD13](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD13.json) | 1 | 2 | 1 | 2 | 2 | N/A | 2 | 1 | 2 |
| [chat-JD13-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD13-1.json) | 2 | 1 | 1 | 2 | 2 | N/A | 2 | 1 | 2 |
| [chat-JD13-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD13-2.json) | 2 | 1 | N/A | 2 | 2 | 2 | 2 | 1 | 1 |
| [chat-JD13-3](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD13-3.json) | 2 | 2 | N/A | 2 | 2 | 2 | 2 | 1 | 2 |
| [review-JD14](../data/academic_benchmark/evaluations/internship-20261013/requests/review-JD14.json) | 1 | 1 | 1 | 2 | 2 | N/A | 2 | 1 | 2 |
| [chat-JD14-1](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD14-1.json) | 1 | 0 | N/A | 2 | 2 | N/A | 2 | 1 | 2 |
| [chat-JD14-2](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD14-2.json) | 2 | 2 | N/A | 2 | 1 | 2 | 2 | 1 | 1 |
| [chat-JD14-3](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD14-3.json) | 2 | 1 | N/A | 2 | 2 | 2 | 2 | 1 | 2 |
| [chat-JD02-4](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD02-4.json) | 2 | 1 | N/A | 2 | 2 | 2 | 2 | 1 | 2 |
| [chat-JD02-5](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD02-5.json) | 2 | 1 | 1 | 2 | 2 | 1 | 2 | 1 | 2 |
| [chat-JD05-4](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD05-4.json) | 2 | 2 | 1 | 2 | 2 | 2 | 2 | 1 | 2 |
| [chat-JD05-5](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD05-5.json) | 2 | 0 | 1 | 2 | 2 | 1 | 2 | 1 | 2 |
| [chat-JD10-4](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD10-4.json) | 2 | N/A | N/A | N/A | N/A | 2 | 2 | 2 | 2 |
| [chat-JD10-5](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD10-5.json) | N/A | N/A | N/A | N/A | N/A | 2 | 2 | 2 | 2 |
| [chat-JD11-4](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD11-4.json) | 2 | 0 | N/A | 2 | 2 | 2 | 2 | 1 | 2 |
| [chat-JD11-5](../data/academic_benchmark/evaluations/internship-20261013/requests/chat-JD11-5.json) | 2 | 1 | N/A | 2 | 2 | 1 | 2 | 2 | 2 |
| [temperature-JD02-0_3](../data/academic_benchmark/evaluations/internship-20261013/requests/temperature-JD02-0_3.json) | 1 | 2 | N/A | 2 | 2 | 2 | 2 | 2 | 2 |
| [temperature-JD05-0_3](../data/academic_benchmark/evaluations/internship-20261013/requests/temperature-JD05-0_3.json) | 1 | 1 | 1 | 1 | 2 | 2 | 2 | 2 | 1 |
| [temperature-JD09-0_3](../data/academic_benchmark/evaluations/internship-20261013/requests/temperature-JD09-0_3.json) | 2 | 2 | N/A | 2 | 2 | 2 | 2 | 2 | 2 |
| [temperature-JD10-0_3](../data/academic_benchmark/evaluations/internship-20261013/requests/temperature-JD10-0_3.json) | 2 | 1 | N/A | 2 | 2 | 2 | 2 | 1 | 2 |
| [temperature-JD11-0_3](../data/academic_benchmark/evaluations/internship-20261013/requests/temperature-JD11-0_3.json) | 2 | 2 | N/A | 2 | 2 | 2 | 2 | 2 | 2 |
| [temperature-JD13-0_3](../data/academic_benchmark/evaluations/internship-20261013/requests/temperature-JD13-0_3.json) | 2 | 2 | N/A | 2 | 2 | 2 | 2 | 2 | 2 |
