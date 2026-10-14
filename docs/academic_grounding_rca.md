# SkillBridge V1 — RCA độc lập về academic grounding

Ngày hoàn tất: **14/10/2026**, Asia/Bangkok. Forensic và ma trận được đóng băng ngày 13/10; người dùng duyệt live ngày 14/10. Đây là RCA diagnostic riêng, không triển khai grounding fix vào production.

## A. Executive Summary

Đã chạy đúng **32 generation + 32 preflight**, không retry, fallback, Review mới hoặc judge. Tất cả 32 response `completed` và parse đúng schema; 30 vượt validator diagnostic, hai bị từ chối. Chi phí tính từ usage và giá niêm yết là **0,24872130 USD**; reservation thiếu usage **0 USD**, dưới trần 3 USD. Thời gian trung bình/trung vị mỗi condition là **7,53 / 5,90 giây**, gồm preflight, generation và validation.

Kết quả quan trọng nhất là **source hierarchy và correspondence không luôn được giữ khi tổng hợp**:

- Bài identification phân biệt đúng CI/regression, CSI data types/network, CPV verbs, SQL, MAI methods, metadata và holdout sources. Không quan sát wrong topic/CLO ID trong tám A/B cases.
- C1–C4, ordering và repetitions của C1/C4 đều trả CI→MAS291/CLO7 đúng. Không quan sát degradation do thêm full profile/JD/Review/history sạch ở câu hỏi atomic này.
- Với history chỉ sai một attribution, D1 đầu sửa CI→CLO7; D2 lại giữ CI→CLO9 ngay trong `claims`, rồi lặp trong `reply`. Repetition D1 cùng input cũng giữ ID sai. **Claim-level schema tự nó chưa có bằng chứng cải thiện grounding.**
- E3 tự mở rộng summary ra Review/profile và gán mới data collection vào ADY201m/CLO7. Nguồn collection trực tiếp là ADY201m/CLO5 hoặc DAP391m/CLO7; Review đầu vào đã phân biệt đúng.
- D2 holdout PFP191 có mapping strings/files/tools đúng, nhưng final reply thêm data structures/OOP mà thiếu refs. E5 holdout mở lại nhiều chủ đề Review khi history chỉ sorting/hashing.

Có **3/24 output chứa reply** có P0: E2-contaminated-D2, E2-contaminated-repeat và E3-same-course. Đây là mẫu diagnostic chọn lọc, gồm seed sai, schema riêng và repetitions; không phải production error rate. Một P0 bị quote check chặn, hai vẫn vượt reference validation. JSON/reference hợp lệ chưa đủ để nghiệm thu semantic.

**H3 và H4 được hỗ trợ một phần ở mức hành vi. H1/H2/H4 chưa được phân biệt hoàn toàn về cơ chế bên trong.** Thay đổi nhỏ nhất nên thử tiếp là internal source excerpts cùng kiểm tra provenance trước khi công bố reply, giữ external `reply/evidence`; kết hợp một thí nghiệm rõ scope summary. Bằng chứng hiện có hỗ trợ chặn một loại lỗi quote/ID cụ thể, chưa chứng minh semantic grounding toàn diện.

Toàn suite sau live: **327 tests passed**, `pip check` sạch. **976 file được bảo vệ**, 43 frozen sources, production prompts/schemas, scoring/data, `.env`, session behavior và artifacts lịch sử giữ nguyên. Profile vẫn **15 môn/122 CLO**.

## B. Existing Architecture

Review nhận toàn profile enriched và JD. Course gồm `course_code`, metadata tùy chọn và CLOs; metadata giữ đúng giá trị nguồn, gồm description/tools. CLO chứa description, score, achievement đã tính trước. Engines không tính lại hoặc gộp điểm khi inference.

Chat nhận profile, JD đúng session, Initial Review và mọi history thành công. Message labels lần lượt là `student_academic_profile`, `current_job_description`, `initial_academic_review`, rồi user/assistant messages. Profile/JD là nguồn facts; Review/history là diễn giải cần kiểm lại. Session kiểm source fingerprint. Diagnostic histories có seed sai nằm riêng, không sửa production sessions.

Production Chat khai báo `reply` trước aggregate `evidence`. References nhận hai dạng:

```json
{"course_code": "MAS291", "clo": "CLO7"}
{"course_code": "ADY201m", "metadata_field": "tools"}
```

Validator kiểm shape, source có trong profile, metadata description/tools không rỗng, mixed/duplicate references. Nó không kiểm từng academic clause được nguồn nào hỗ trợ. Production prompt đã yêu cầu giữ learning verbs, band từng CLO, phân biệt curriculum/personal use, sửa Review/history sai và recheck summary. Forensic không hỗ trợ cách giải thích đơn giản rằng chỉ cần thêm cùng các lời nhắc đã hiện diện.

Runner riêng tại [academic_grounding_rca.py](../research/diagnostics/academic_grounding_rca.py) tái sử dụng Responses/Pydantic, preflight, trace recording và cost ledger. Production không import diagnostic. C giữ nguyên production prompt/schema; D/E dùng cùng diagnostic copy chỉ thay output contract. D2 khai báo `claims` trước `reply/evidence`, hỗ trợ CLO và metadata excerpts. Schema không tự enforce atomicity, semantic entailment hoặc closure giữa mapping và final reply.

## C. Forensic Findings

[forensic_findings.json](../data/academic_grounding_rca/forensic_findings.json) giữ exact messages/replies/evidence, Review/history trước lỗi, actual input hashes, đúng/sai canonical sources và occurrence. Raw output JSON đã so với parsed output. Lexical search chỉ định vị đoạn để đọc.

| Historical case | Exact user message | Claim/ID sai | Canonical source có trong input | First occurrence |
|---|---|---|---|---|
| JD05, Chat 2 | Mình cần xem xét bổ sung những kiến thức hoặc công cụ nào? | MAS291/CLO9 — “Construct and interpret confidence intervals...” | CI→CLO7; regression→CLO9 | Reply lượt 2. Lượt 1 đã dẫn cả hai đúng; Review không có association sai này. |
| JD10, Chat 4 | Tóm tắt những kiến thức đã có và những công nghệ chuyên biệt chưa được hồ sơ xác nhận. | MAS291/CLO9 — “confidence intervals... and simple linear regression...” | CI cần CLO7 và regression cần CLO9 | Summary tự thêm CI; Review và ba assistant replies trước đó không nêu CI. Session không có history JD05. |
| JD11, Chat 1 | Mình có những nền tảng học thuật nào liên quan tới Backend Engineering? | CSI106/CLO4 — “Describe how different data type is stored...” | Data types/bit patterns→CLO3; network→CLO4 | Reply đầu tiên, chưa có assistant history. Review dùng CLO4–5 đúng cho network/OS. |

Ba raw responses đều completed, snapshot `gpt-5.4-mini-2026-03-17`; input lần lượt **21.218 / 22.104 / 19.904 tokens**. ID sai nằm trong prose và aggregate evidence, không chỉ thiếu reference. MAS7/MAS9 cùng `9.43/excellent`; CSI3/CSI4 cùng `8.1/good`. Kiểm số/band riêng không phát hiện các lỗi này.

Đã đọc findings của **115 historical output records** thuộc ba run, kiểm raw **17 operation khác nhau**, gồm ba primary cases, 12 representative findings và ba controls. Annotations cũ giữ nguyên; đây không phải regrade mọi claim của 115 output.

| Nhóm taxonomy tổng quát | Representative raw case | Đánh giá lại |
|---|---|---|
| Within-course misbinding | Ba P0 trên | Mô tả đúng bị gắn ID khác cùng môn. |
| Missing support / compound compression | Internship Review JD01/JD05 | Regression MAI5 đúng trong prose nhưng thiếu aggregate ref, P1; PCA bị gộp vào nhóm CLO không chứa PCA, P0. JD05 omission refs MAS8/MAI4 được ghi P1; không tự coi omission là selection failure. |
| Cross-course / unsupported specificity | Internship Review JD03/JD10 | DAP1–2 bị coi image-specific; broad Python/libraries thành pandas/numpy trong legacy sources không nêu tên. |
| Performance distortion | Internship Review JD07 | DAP1=`8.45/good`, AIL1=`7.56/good`; “good và excellent” không khớp refs. |
| Choice→personal use / synthesis | Internship Review JD12 | Comment thừa nhận at-least-one không xác định Git; conclusion lại xác nhận sử dụng GitHub. |
| SQL source / JD modality | Internship Chat JD12 turn 3 | SQL gắn DAP7 thay ADY7; preferred/Nice-to-have SQL đổi thành Required. |
| Cognitive-verb upgrade | Internship Chat JD14 turn 1 | Implement object detection CPV8 bị gộp thành implement face recognition; CPV9 chỉ Explain. |
| Outcome→completed artifact | Five-JD Chat JD10 turn 1 | Intended capstone + grade thành “đã làm workflow dự án”; P1 trong bối cảnh học thuật. |
| History propagation | Metadata-models Chat JD11 gpt41 | Association ADY7→API có occurrence cụ thể trong history, rồi bị lặp sau probe sửa. |
| Source-family confusion | Metadata-models Review JD01 legacy gpt41 | Sinh metadata ref khi actual legacy input không có metadata; validator chặn. Không backfill enriched metadata. |

Taxonomy gồm 13 nhóm, tách identification/attribution, interpretation, compression, summary invention và propagation. Specific IDs là regression fixtures, không phải runtime rules.

Controls cùng Mini medium: `chat-JD05-1` dẫn CI7/regression9 đúng; `chat-JD01-3` giữ CPV8 Understand/Implement và CPV9 Explain, `8.81/excellent`; `chat-JD11-3` dẫn API ADY5/DAP5–6/AIL1 và giới hạn framework đúng. Chúng cho thấy model có thể làm đúng, không phơi bày selection process của lượt sai.

## D. Experiments

Mọi lượt giữ snapshot **gpt-5.4-mini-2026-03-17 / medium / 8.192 output / timeout 180 giây**; temperature omitted, retries=0, `store=False`, `truncation=disabled`. Preflight/generation giữ cùng model, reasoning, input, prompt và schema. Requested/resolved model giống nhau ở cả 32 output.

Plan SHA-256 giữ nguyên:

```text
54ea1fe098579d731af9c244b823d68f45454187357d89a3675c49320d5fd2e3
```

[plan.json](../data/academic_grounding_rca/plan.json), [conditions.json](../data/academic_grounding_rca/conditions.json), [expected_evidence.json](../data/academic_grounding_rca/expected_evidence.json), [histories.json](../data/academic_grounding_rca/histories.json) và schemas giữ nguyên sau freeze. Scenarios: S1 MAS CI/regression; S2 CSI data/network; S3 CPV verbs; S4 DBI/ADY SQL versus DAP project/bands; S5 MAI optimization/regression/PCA/SVM; S6 metadata/tool choices; S7 holdout PFP strings/files/framework/IDE; S8 holdout CSD graph/sort/hash/achievement. Holdouts không dùng để thiết kế prompt, chạy cuối; không tuning sau output.

| Comparison | Inputs / changed variables | Expected | Actual behavior và giới hạn |
|---|---|---|---|
| A/B, tám scenarios | Candidate course pools, source/excerpt/relation task; không Chat | Phân biệt topic/source, direct/related và tools/verbs | Topic/source IDs đúng, kể cả holdouts. S4/S8 underclassify bands; CSI compound dùng metadata alternative đúng nhưng duplicate ref. Pool/task khác Chat nên không quy khác biệt cho riêng schema. |
| C1→C2→C3→C4 | MAS-only→full profile→JD05/Review→history trước lỗi; production prompt/schema; cùng atomic question | CI→MAS7 trong mọi context | Cả bốn đúng. Input 5.778→17.554→19.937→21.219 tokens. Đây là thay câu hỏi lỗi lịch sử bằng atomic question, không exact replay. |
| D, bốn cặp | S1/S6/S7/S8, cùng question/input/diagnostic prompt; đổi output contract/schema/order | Mapping/reply/aggregate giữ nguồn đúng | S1/S6 đều đúng; S7-D2 thiếu refs cho extra OOP/data structures; S8 cả hai giữ số/band đúng nhưng thiếu companion scores trong so sánh thêm. D2 đổi representation, size và order cùng lúc. |
| E clean/contaminated + D2 | Cùng context; contaminated chỉ đổi CI7→CI9 trong một reply và ref | Summary giữ/sửa nguồn theo profile | Clean D1/D2 đúng. Contaminated D1 sửa đúng, D2 sai ngay mapping rồi reply. Một pair hỗ trợ context effect nhưng repetition cho thấy variability. |
| E3, E4, E5 | Các histories độc lập; same-course, multi-source, short holdout | Retain topics/sources, không tạo association mới sai | E4 đúng. E3 mở rộng và tạo ADY7→collection sai; E5 thêm facts Review ngoài short history. Các E này không phải paired causal ablation. |
| Ordering | So C2; chỉ đảo CLO arrays, giữ course order/metadata/mọi giá trị | Nguồn CI không đổi | C2-reversed vẫn MAS7, token count bằng C2. Một exploratory check. |
| Repetitions | C1, C4, contaminated E2-D1, mỗi condition lặp định trước một lần | Giữ mọi kết quả, đo variability | C1/C4 ổn định CI7. E2-D1 đầu CI7, repeat CI9. Không chọn output tốt. |
| Verified mapping | So D-S1-D1, thêm mapping CI7/regression9 xác nhận trước | Synthesis giữ nguồn đã cho | Đúng như baseline đã đúng. Không cho thấy repair khi contaminated hoặc khi baseline sai. |

C question nguyên văn: **“Trong hồ sơ học thuật này, CLO nào xác nhận nội dung confidence intervals?”** D/E giữ production grounding/style/Strict Option A rules, chỉ thay contract hai fields bằng contract theo schema. Không output nào của condition mới trở thành input condition khác.

Từng raw trace dưới `live/requests/` có full request/response, parser output và metrics. Bảng sau dùng **V**=combined validator passed, **R**=reference duplicate rejected, **Q**=quote rejected; P labels là manual findings, không suy từ API status.

| Operation / raw trace | Validation | Manual result chính |
|---|---|---|
| [AB-S1](../data/academic_grounding_rca/live/requests/AB-S1.json) | V | CI7, regression9 và compound đúng |
| [AB-S2](../data/academic_grounding_rca/live/requests/AB-S2.json) | R | CSI3/4 đúng; metadata description hỗ trợ compound; ref lặp với hai excerpts |
| [AB-S3](../data/academic_grounding_rca/live/requests/AB-S3.json) | V | CPV8/9 và Explain≠Implement đúng |
| [AB-S4](../data/academic_grounding_rca/live/requests/AB-S4.json) | V | SQL sources đúng; 2 band units trả insufficient, P1 theo frozen expectations |
| [AB-S5](../data/academic_grounding_rca/live/requests/AB-S5.json) | V | MAI4/5/6/7 đúng; không bắt cite mọi alternative |
| [AB-S6](../data/academic_grounding_rca/live/requests/AB-S6.json) | V | Metadata listing/at-least-one/individual-use limits đúng |
| [C1](../data/academic_grounding_rca/live/requests/C1.json) | V | MAS7 đúng, source scoped |
| [C2](../data/academic_grounding_rca/live/requests/C2.json) | V | Full profile vẫn MAS7 |
| [C3](../data/academic_grounding_rca/live/requests/C3.json) | V | MAS7 đúng; closing offer P2 |
| [C4](../data/academic_grounding_rca/live/requests/C4.json) | V | History sạch, MAS7 đúng |
| [D-S1-D1](../data/academic_grounding_rca/live/requests/D-S1-D1.json) | V | CI7/LR9, điểm và bands đúng |
| [D-S1-D2](../data/academic_grounding_rca/live/requests/D-S1-D2.json) | V | Mapping và reply đúng; baseline D1 cũng đúng |
| [D-S6-D1](../data/academic_grounding_rca/live/requests/D-S6-D1.json) | V | Tools/choices đúng; redundant offer P2 |
| [D-S6-D2](../data/academic_grounding_rca/live/requests/D-S6-D2.json) | V | Metadata/CLO boundaries đúng |
| [E1-clean](../data/academic_grounding_rca/live/requests/E1-clean.json) | V | Bốn topics đúng, đúng từng score/band |
| [E1-clean-D2](../data/academic_grounding_rca/live/requests/E1-clean-D2.json) | V | Mapping/reply bốn topics đúng |
| [E2-contaminated](../data/academic_grounding_rca/live/requests/E2-contaminated.json) | V | Sửa CI9→CI7 trong facts, không acknowledge tường minh; P2 offer |
| [E2-contaminated-D2](../data/academic_grounding_rca/live/requests/E2-contaminated-D2.json) | Q | P0 CI→CLO9 ở claims[0] và reply; propagation; P2 offer |
| [E3-same-course](../data/academic_grounding_rca/live/requests/E3-same-course.json) | V | P0 mới ADY7→collection; EDA over-specific và summary scope P1 |
| [E4-multiple-sources](../data/academic_grounding_rca/live/requests/E4-multiple-sources.json) | V | DBI5/MAI4/6/7 đúng; redundant offer P2 |
| [C2-reversed](../data/academic_grounding_rca/live/requests/C2-reversed.json) | V | Đảo order vẫn MAS7 |
| [C1-repeat](../data/academic_grounding_rca/live/requests/C1-repeat.json) | V | Vẫn MAS7 và 9.43/excellent |
| [C4-repeat](../data/academic_grounding_rca/live/requests/C4-repeat.json) | V | Vẫn MAS7; profile scan xác nhận absence ở CLO khác |
| [E2-contaminated-repeat](../data/academic_grounding_rca/live/requests/E2-contaminated-repeat.json) | V | P0 CI→CLO9, quote không có trong CLO9; reference validator vẫn passed |
| [D-S1-verified-mapping](../data/academic_grounding_rca/live/requests/D-S1-verified-mapping.json) | V | Giữ CI7/LR9 đúng, không chứng minh mapping sửa lỗi baseline |
| [AB-S7](../data/academic_grounding_rca/live/requests/AB-S7.json) | V | PFP4/5, tools, FastAPI absence đúng với supplied PFP-only input |
| [AB-S8](../data/academic_grounding_rca/live/requests/AB-S8.json) | V | CSD5/6/7 đúng; 3 band units trả related, P1 theo expectations |
| [D-S7-D1](../data/academic_grounding_rca/live/requests/D-S7-D1.json) | V | Strings/files/framework/IDE boundaries đúng |
| [D-S7-D2](../data/academic_grounding_rca/live/requests/D-S7-D2.json) | V | Correct mapping; final reply thêm OOP/data structures, thiếu PFP6/7 refs, P1 |
| [D-S8-D1](../data/academic_grounding_rca/live/requests/D-S8-D1.json) | V | CLO5–7=6.06/basic, không course-level excellent; companion-score omission P1 |
| [D-S8-D2](../data/academic_grounding_rca/live/requests/D-S8-D2.json) | V | Mapping/values đúng; same omission P1 và offer P2 |
| [E5-holdout](../data/academic_grounding_rca/live/requests/E5-holdout.json) | V | Sorting/hashing đúng; 76 added assertions chủ yếu Review, scope P1 và offer P2 |

**Ba live P0, với canonical contradiction:**

1. E2-D2: “Confidence intervals: có bằng chứng trực tiếp ở MAS291/CLO9”; claims[0] cũng dùng source9 với excerpt CI. CLO9 là regression; excerpt thuộc CLO7. Wrong mapping có trước final reply trong observable output. Đây là propagation association seeded sai, không chứng minh selection nội bộ ban đầu từng đúng.
2. E2-repeat: “Confidence intervals: Bạn có bằng chứng học tập trực tiếp ở MAS291/CLO9”. Cùng prompt/input/schema/settings với E2-D1 đầu đã sửa đúng. Điểm/band đúng không sửa wrong binding; aggregate thiếu CLO7.
3. E3: “ADY201m/CLO7 ... gồm data collection, data wrangling, EDA...”. ADY7 nêu data understanding/preprocessing, không collection; ADY5 nêu collecting data, DAP7 nêu collection. Review input dẫn DAP7 collection và ADY7 preprocessing riêng đúng; history chỉ MAS5–9. Association collection→ADY7 mới xuất hiện ở summary. Metadata ADY description có data gathering ở phạm vi course, nhưng không xác lập graded CLO7. Wrangling/preprocessing được chấp nhận như paraphrase; EDA-specific scope ghi P1 vì có semantic overlap, không mặc định mọi synonym mismatch là P0.

A/B band classifications có hạn chế contract: excerpt chỉ quote description, còn achievement nằm ở sibling field trong source object. Model trả insufficient/related dù actual field là basic. Ghi riêng năm underclassified units theo frozen expectations; không coi đây là bịa numeric grade hay bằng chứng model luôn không đọc được scores. Chat D-S8-D1/D2 giữ đúng 6.06/basic.

## E. Atomic Claim Metrics, Usage và Validation

[manual_annotations.json](../data/academic_grounding_rca/manual_annotations.json) lưu original spans, model/acceptable/actually provided sources, result, severity và giải thích. [annotation_protocol.json](../data/academic_grounding_rca/annotation_protocol.json) giữ rubric trước live. Annotations mới không thay historical labels hoặc frozen expected file.

**132 frozen assessment units** được tách thành **156 asked atomic assertions** khi phân rã tool-list memberships, hai IDE personal-use boundaries và face/tracking verb boundaries từ exact questions/targets. Expected facts/sources không đổi. Reply facts đếm một lần cho mỗi topic/property; source-only excerpts không tự tạo thêm student assertions. Mapping audit của D2 được ghi riêng để tránh đếm lại cả claims và reply. Counts phụ thuộc quy ước này, không phải denominator từ mọi từ trong output.

| Mẫu số | Được hỏi | Tự thêm | Tổng được trả lời |
|---|---:|---:|---:|
| Atomic assertions được kiểm | 156 | 345 | 501 |
| Direct đúng | 128 | 333 | 461 |
| Related/boundary đúng | 18 | 0 | 18 |
| Absence đúng | 3 | 8 | 11 |
| Wrong attribution | 2 | 1 | 3 |
| Relation underclassification về bands | 5 | 0 | 5 |
| Interpretation over-specific | 0 | 1 | 1 |
| Missing required references cho topic có thật | 0 | 2 | 2 |

Không có asked unit bị bỏ hẳn; answered không có nghĩa correct. Ba P0 atomic bindings nằm trong ba Chat outputs; tám P1 atomic findings gồm năm band underclassifications, một EDA scope interpretation và hai missing refs. Ngoài ra có P1 ở output level cho summary scope và missing companion scores; không gộp chúng thành một unexplained success percentage. Có **7 output có P1**, **7 có P2**, các tập có overlap với P0.

Không quan sát numeric score/band bịa, nâng CPV learning verb, xác nhận FastAPI hoặc xác nhận cá nhân dùng mọi tool trong các live probes tương ứng. Đây là observation theo sample, không nghiệm thu các regression ngoài phạm vi. E3/E5 có **106/76 added assertions** theo convention; phần lớn có canonical support. Added supported facts ngoài summary scope và invented association sai được tách riêng.

Source validation độc lập ở [postrun_checks.json](../data/academic_grounding_rca/postrun_checks.json): **65/65 quoted source references có trong actual input**, **64/65 excerpts nguyên văn đúng source**. **13/14 quoted-output operations** qua literal provenance. AB-S2 có hai exact excerpts từ cùng metadata field, source support hợp lệ, nhưng duplicate-reference policy từ chối. Runner metric `quote_provenance_validation` tổng hợp cả reference checks; audit này tách literal quote khỏi duplicate failure.

CSI metadata.description là alternative hợp lệ cho compound data representation/networking vì source thực có cả hai nội dung; adjudication được ghi mới, không sửa frozen expected file. Alternatives không bắt buộc cùng được cite. A/B PFP-only không bị chấm thiếu ADY/DAP sources đã loại khỏi input.

| Technical dimension | Kết quả |
|---|---|
| Generation HTTP / preflight HTTP / total | 32 / 32 / 64 |
| Completed / parsed đúng schema | 32/32 / 32/32 |
| Combined validator passed | 30/32 |
| Timeout / incomplete / retry / parser failure | 0 / 0 / 0 / 0 |
| Largest actual input + output reserve | 21.219 + 8.192, trong context 400.000 |
| Output nhiều nhất | 5.196, dưới ceiling 8.192 |
| Parsed artifacts | 30 accepted outputs; cả 32 parsed attempts còn trong original traces |
| Known cost / unknown reservation | 0,24872130 / 0 USD |

Giá kiểm lại ngày 14/10 từ [OpenAI Docs — GPT-5.4 Mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini): input **0,75 USD/M**, cache **0,075 USD/M**, output **4,50 USD/M**. Dự trù frozen 2,715648 USD dùng 64.000 uncached input và hết ceiling; assumption này không cắt context. Cumulative reservations theo preflight thực tế không thay thế known cost đã được tính từ usage.

| Usage toàn run | Tokens |
|---|---:|
| Input | 472.182 |
| Cached input | 364.544 |
| Output, đã gồm reasoning | 31.256 |
| Reasoning subset | 17.369 |
| Total input + output | 503.438 |

Cache/input nhỏ hơn assumption và output dưới ceiling giải thích cost thấp. Reasoning không tính hai lần. Chi phí là estimate từ usage theo published prices, không phải hóa đơn billing. [execution_summary.json](../data/academic_grounding_rca/execution_summary.json) có đủ usage/cost/latency từng operation.

| Schema/task | n | Latency mean / median, giây |
|---|---:|---:|
| Identification | 8 | 7,12 / 6,00 |
| Chat contract | 18 | 6,64 / 4,34 |
| Claim-level contract | 6 | 10,74 / 9,37 |
| Toàn bộ | 32 | 7,53 / 5,90 |

Đây là condition latency gồm preflight+generation+parsing/validation; không có isolated model-generation timer. D2 input tăng **270 tokens** ở từng cặp schema do contract/schema. Output D1/D2: S1 **460/675**, S6 **899/1.593**, S7 **847/2.329**, S8 **632/2.660**, E1 **435/1.110**, E2 **921/786**. Không suy latency/cost tăng là effect thống kê của schema: output/reasoning allocation và caching khác nhau, chỉ có một cặp mỗi scenario.

## F. Hypothesis Assessment

| Hypothesis | Evidence hỗ trợ | Evidence trái chiều | Confidence định tính | Giới hạn |
|---|---|---|---|---|
| H1 Evidence identification | Explicit E2-D2 mapping chọn wrong source dưới contaminated full context | A/B topical sources đúng trên tám scenarios, C atomic đúng, historical controls đúng. Band underclassification khác với wrong topic ID | Không được hỗ trợ trong isolated topical sample; tổng quát **inconclusive** | Không có isolated mapping-only với chính contaminated E2 context; chưa tách copy-history khỏi lookup failure trong context đó |
| H2 Claim attribution | Production aggregate không bắt claim binding; D-S7-D2 thêm facts thiếu refs ở reply dù mapping facts ban đầu đúng | D2 vẫn sai ngay claims[0]; D1 baselines cũng làm đúng; verified mapping không cải thiện baseline đã đúng | **Inconclusive**; nguyên nhân duy nhất do flat schema chưa có bằng chứng | D2 đổi representation/order/size; không biết nguồn từng được chọn nội bộ; mapping explicit không bảo đảm reply closure |
| H3 Context interference | Clean E1-D2 đúng, contaminated E2-D2 sai với một changed attribution; E3/E5 kéo topics từ Review ra summary | C1–C4/reorder vẫn đúng; E2-D1 đầu đúng; same-input repetition đổi kết quả. Context dưới window | **Partially supported**, đặc biệt history/summary context | Pair ít; source hierarchy failure không deterministic. Scope summary có thể được model hiểu bao gồm Initial Review |
| H4 Synthesis/summary | E3 tạo collection→ADY7 mới; D-S7-D2 final reply thêm OOP/data structures ngoài mapping; summary expansion có ở holdout | E1/E4 summaries đúng; E2-D2 CI mapping đã sai trước final reply, nên không chứng minh selected-right-then-lost | **Partially supported** ở hành vi, cơ chế H1/H2/H4 còn **inconclusive** | Không nhìn hidden reasoning; source compression/interpretation/context có thể cùng góp phần |

Hypothesis khác: **output variability** được quan sát ở predetermined E2 repeat; input/model/settings giữ nguyên mà attribution đổi. **Experimental source-family/quote contract ambiguity** có thể góp phần band underclassification. Annotation uncertainty có ở EDA scope và summary scope; đã ghi nhẹ hơn exact CI misbinding. Data corruption, grade-calculation bug, context overflow, truncation hoặc output exhaustion không giải thích các live P0 quan sát.

Operational conclusion có bằng chứng là model đôi lúc **không dùng profile để sửa association từ history**, và có thể **thêm/gộp claims khi viết summary mà không giữ exact source**. Chưa thể khẳng định một hidden selection process hoặc schema duy nhất là root cause.

## G. Generalization và Historical Comparison

Holdouts giữ strings/files/IDE, graph/sort/hash và bands đúng. D-S7-D2 cũng tạo missing refs ở final reply; E5 mở rộng summary ngoài short history. Vì vậy các vấn đề mapping-to-reply closure và topic scope xuất hiện ngoài MAS/CSI. Không quan sát holdout P0, nhưng có P1; D2 chưa chứng minh transfer improvement.

Historical three P0 và live P0 đều có valid IDs, correct sources trong input, thường cùng scores/bands nên exact attribution là điểm cần kiểm. Historical JD10 invention và live E3 mới cùng thể hiện summary source mixing; seeded E2 cho thấy propagation thật. Kết quả C không tái tạo broad-question JD05 lỗi vì câu hỏi đã thay thành atomic. Không dùng số lỗi của các run khác profile/prompt/question/budget làm causal model comparison.

D2 không thắng D1 trong observed attribution: S1/S6 đều đúng, S7-D2 thêm omission, E2-D2 sai khi D1 đầu đúng. Repetition D1 cũng sai nên không kết luận D2 gây lỗi. Quote check chặn được E2-D2, cho thấy giá trị của observability/provenance control, khác với chứng minh tăng raw semantic accuracy.

Natural Vietnamese nhìn chung dễ đọc ở câu hỏi hẹp. Các redundant offers và broad summaries giảm continuity; không áp word limit, số bullet cố định hoặc coi dài tự nó là P2. E3/E5 bị ghi scope findings vì nội dung ngoài history mục tiêu, với caveat Initial Review cũng nằm trong context. Các offer nhắc CV chưa tạo CV content; không tự nâng chúng thành academic P0.

## H. Engineering Recommendations

Xếp hạng dưới đây dựa trên **loại benefit đã quan sát và mức uncertainty**, không phải bảo đảm giảm toàn bộ P0. Đây là recommendations cho task tiếp theo; production chưa thay đổi.

| Hạng / intervention | Grounding benefit | Generalizability | Complexity | Runtime cost | Compatibility |
|---|---|---|---|---|---|
| 1. Internal source excerpts + deterministic source/quote gate trước publish | Đã chặn một completed P0 CI quote/ID trong D2; không kiểm semantic entailment hoặc unquoted added claims | CLO/metadata và nhiều courses; không hardcode IDs | Vừa: internal contract, adapter, error handling; tách duplicate refs khỏi nhiều excerpts hợp lệ | Một generation, thêm schema/output tokens; không judge | Giữ external reply/evidence, natural Vietnamese, Strict Option A; failed output cần reviewer, không biến lỗi thành academic gap |
| 2. Làm rõ summary topic boundary của chat history, profile vẫn là authority | E3/E5 expansion ở development/holdout cho lý do thử giảm unnecessary claims và source mixing | Chung cho summary/follow-up | Thấp–vừa; phải kiểm user yêu cầu summary Review hay Chat | Có thể cùng generation, ít output hơn; chưa đo benefit trực tiếp | Giữ full profile/history và referent resolution; không tự cắt dữ liệu |
| 3. Claim mapping cùng final-reply closure checks/representation | D-S7-D2 chứng minh mapping đúng chưa đủ; cần source cho mọi added reply fact | Theo cấu trúc facts chung | Vừa–cao; cần giữ ngôn ngữ tự nhiên và adjudicate paraphrases | Một call có thể đủ nhưng schema lớn; thêm verifier LLM chưa có bằng chứng | Adapter giữ external schema; không biến thành template cố định hoặc assume D2 tự tốt hơn |
| 4. Canonical score/band rendering sau khi source binding đúng | Historical value errors có; live numeric values đúng. Không giải quyết CI7/9 cùng score | Mọi assessed outcomes | Thấp–vừa | Không cần thêm generation | Không đổi scoring, không tạo skill-level score; ưu tiên thấp hơn source correspondence |
| 5. Candidate indexing/retrieval/context narrowing nếu mapping-only tests vẫn sai | Isolated identification và C hiện chưa hỗ trợ đây là fix chính | Có thể course-agnostic nếu giữ recall | Vừa; cần evidence coverage và alternatives | Phải đo; không mặc định cần vector DB | Chưa có cơ sở bỏ full context hoặc thay session behavior |

**Thay đổi nhỏ nhất nên prototype:** internal excerpts và kiểm literal source provenance, có adapter giữ response public. Chỉ tuyên bố chặn loại mismatched quote/source đã thấy, và đo cost, completion, false rejection, semantic correctness/holdouts riêng. CSI duplicate case cho thấy cần thiết kế source record chứa nhiều excerpts thay vì coi hai excerpts hợp lệ là hai source identities; aggregate evidence vẫn unique. Gate sẽ không tự chữa source semantic support, score/source coupling hoặc final-reply drift.

Thí nghiệm tiếp theo hữu ích nhất là cùng contaminated E2 context ở ba chế độ mapping-only, verified external mapping rồi synthesis, và bounded summary scope; có repetitions định trước/holdouts. Đây là đề xuất cho ngân sách mới, không dispatch thêm trong run đã hết 32 operations generation.

## I. Limitations, Integrity và Handoff

Mẫu gồm 32 lượt, tám scenarios, chỉ ba conditions có một repeat. Paired results không đủ statistical significance hoặc causality. A/B khác Chat về task/pool/schema; C thay câu hỏi; E histories synthetic; D2 đổi nhiều output properties cùng lúc. Verified mapping chỉ thử một baseline vốn đúng. Mapping output là observable content, không hidden reasoning.

Manual metrics có subjective granularity và severity. Năm band underclassifications chịu description-only excerpt caveat; EDA scope có overlap; E3/E5 summary scope có ambiguity về Initial Review. Toàn bộ outputs được đọc nguyên bản; counts 501 là distinct assertions theo convention được công khai, không phải population accuracy hoặc exhaustive lexical propositions. Raw results và frozen expectations giữ nguyên để reviewer adjudicate lại.

Forensic historical sample chọn từ findings, không ngẫu nhiên; chỉ kiểm raw 17 operation và 19 fault assertions chọn lọc, không regrade 115 output đầy đủ. Các raw artifacts cần cho primary cases có sẵn. Không có internal selection trace; H1/H2/H4 vẫn cần phép thử mới để phân biệt.

Artifacts bàn giao: frozen plan/scenarios/conditions/expected/history/schemas; historical forensic; live raw traces và accepted parsed outputs; ledger/usage; [manual annotations](../data/academic_grounding_rca/manual_annotations.json); [execution summary](../data/academic_grounding_rca/execution_summary.json); [postrun checks](../data/academic_grounding_rca/postrun_checks.json); [summary](../data/academic_grounding_rca/summary.json); [integrity check](../data/academic_grounding_rca/integrity_check.json). Offline analysis helpers không chạy inference, không production import.

Post-live checks: **327 tests passed**, **pip check sạch**, **976 protected files unchanged**, **43 frozen source hashes passed**, **Chat/Review schemas unchanged**, raw trace/output fingerprints preserved, profile **15/122**. Plan và production defaults vẫn giữ nguyên. Không chạy lại attempt lỗi, không chọn output tốt hoặc sửa source/previous replies để xóa lỗi.

RCA đã hoàn tất trong phạm vi được duyệt. Classroom MVP vẫn cần reviewer/source visibility; nguồn có đủ và parser passed chưa đủ để dùng Chat như authoritative academic advice. Không tuyên bố semantic acceptance toàn bộ 15 JD hoặc triển khai grounding fix từ mẫu này.
