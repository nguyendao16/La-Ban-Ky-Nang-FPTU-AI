# SkillBridge V1 — Evidence-bound Response Prototype & Controlled Grounding Evaluation

Ngày hoàn tất live/manual review: **14/10/2026**, Asia/Bangkok. Người dùng phê duyệt riêng plan prototype ngày 14/10. Đây là nghiên cứu diagnostic độc lập; không tích hợp vào production.

## A. Executive Summary

Đã chạy đúng **32 generation + 32 preflight = 64 physical HTTP operations**, snapshot **gpt-5.4-mini-2026-03-17 / medium / 8.192 output / 180 giây**, không retry, fallback, Review mới, judge hoặc generation sửa/formatting. Chi phí từ usage và giá standard là **0,51454170 USD**; reservation chưa biết **0 USD**, dưới trần 3 USD. Đây không phải hóa đơn.

**Chưa có bằng chứng Path B giảm raw academic P0 so với schema hiện tại.** A và B đều có **13/16 response completed**, không quan sát P0 trong 26 reply có text. Cả sáu condition tổng hợp JD07/S8 — hai S0, hai S1 và hai repetitions — đều `incomplete: max_output_tokens`, không có public text; mỗi request báo output=reasoning=8.192. Không chấm những câu trả lời không tồn tại thành academic P0 hoặc semantic success.

Findings chính:

- Gate B pass **13/13 output có thể kiểm**, với **93 academic quotes + 1 JD quote** nguyên văn đúng nguồn; **0 reject/withheld**, 0 false rejection quan sát được. Không có wrong-quote opportunity để đo detection sensitivity trong live.
- B vẫn đặt academic facts vào `general_explanation` không có local sources ở **3/13 completed outputs**, gồm **9 atomic assertions**. Facts và aggregate refs đúng; representation chưa bảo đảm segment-local correspondence.
- S6-S0 mở rộng summary khỏi history ở A lần đầu và B cả hai lần. **S1 giữ đúng conversation scope ở cả A và B**. A-S0 repetition tự giữ scope đúng, nên không quy causal guarantee cho một pair.
- B-S6-S0 đầu còn bỏ **Central Limit Theorem** và so sánh bands PFP191/CLO1–6 mà không giữ từng numeric score. Các bands được nêu vẫn đúng, không có wrong-grade P0.
- Public usable-response rate theo factual truth + essential completeness + requested scope: **A 12/16=75%**, **B 11/16=68,75%**. Local B-only contract defects được báo riêng; không dùng requirement này để giả tạo academic advantage cho A.

**Khuyến nghị: lựa chọn 2 — chỉ cân nhắc summary-scope clarification trong một task production riêng có kiểm thử tiếp; giữ schema hiện tại.** Evidence-bound adoption còn **inconclusive**. S8 completion failure của cả hai arms cần nghiên cứu riêng trước khi hứa hỗ trợ full-JD summary cho classroom MVP.

Offline trước live: **376 tests passed**, `pip check` sạch. Integrity sau inference giữ nguyên **1.451 historical/production files**, **50 frozen execution inputs/artifacts**, và **110 original inference artifact files**. Profile vẫn **15 môn/122 CLO**, 15 metadata, bốn `tools=""`. Post-live checks cuối nằm trong [postrun_checks.json](../data/academic_grounding_prototype/postrun_checks.json).

Sau live/manual review, toàn suite chạy lại đạt **376 tests passed trong 145,01 giây**, `pip check` sạch. [Execution summary](../data/academic_grounding_prototype/execution_summary.json) và [study analysis](../data/academic_grounding_prototype/study_analysis.json) giữ counters, usage, metrics và kết luận cuối; không phát sinh generation/preflight sau ma trận.

## B. Prototype Architecture

Code độc lập: [evidence_bound_response.py](../research/diagnostics/evidence_bound_response.py), fixtures và analysis helpers cùng thư mục. Production không import diagnostic. Không sửa engines, prompts, schemas, validators, builder/scoring, defaults, sessions, `.env` hoặc artifacts lịch sử.

**A:** production `AcademicChatResponse` chứa `reply` và aggregate `evidence`. A-S0 giữ nguyên toàn bộ instructions, bao gồm metadata rules. Chỉ dùng validator hiện có; mọi đánh giá semantic là analysis riêng.

**B:** `EvidenceBoundResponse` chỉ chứa `segments`. Segment gồm `kind`, `text`, `academic_sources`, `jd_excerpt`. Sources nhận đúng hai identity families CLO/metadata, thêm exact `source_excerpt`; không nhận score/band hoặc mixed identity. B không khai báo public reply/evidence trong model output.

| Kind | Structural policy |
|---|---|
| `academic_claim` | Ít nhất một academic source hợp lệ |
| `jd_requirement` | Không có academic sources; cần exact JD excerpt không rỗng |
| `not_evidenced` | Được không có source; related academic sources được phép |
| `general_explanation` | Không có academic/JD sources; chỉ dùng lời nối |

Runtime không thể xác nhận semantic của `kind` bằng kiểm chuỗi. Một academic claim bị giấu trong `general_explanation` có thể pass; đánh giá thủ công ghi `kind_misclassification` và semantic false acceptance.

Gate kiểm course/CLO/metadata thuộc profile thực sự gửi, field không rỗng, quote là literal substring của đúng CLO description hoặc metadata field và JD quote thuộc JD đang gửi. Không chuẩn hóa spelling/newlines, không yêu cầu quote dài tối thiểu, không so public paraphrase với nguyên văn description.

Nhiều excerpt từ một source được giữ nguyên và chấp nhận trong cùng hoặc khác segments. Chỉ aggregate evidence cuối loại identity trùng, theo thứ tự sử dụng đầu tiên. Đây là khác biệt cần thiết với false rejection của RCA AB-S2.

Adapter nối nguyên văn text theo thứ tự bằng `"\n\n"`. Có thể có nhiều claims trong một segment nếu cần nhiều sources; không ép số segments, câu, đoạn hoặc từ. Adapter không thêm câu giải thích, đổi learning verb/grade, tìm thêm refs hoặc sửa nội dung.

Khi gate reject, original raw/parsed output và từng lỗi được giữ, public output bị withheld. `raw_views` là bản đọc analysis-only, không phải fallback. Không retry hoặc commit vào session thật.

**Giới hạn:** literal provenance không chứng minh entailment, performance đúng, JD modality đúng hoặc mọi claim đều có nguồn. Quote đúng về preprocessing có thể được gắn vào claim collection sai. Score/band, curriculum-versus-personal-use, verbs và optional/OR đều được chấm thủ công.

## C. Experimental Design

Full profile, đúng JD/Review, frozen history và câu hỏi giống nhau trong từng cặp. Mọi Review lấy từ run `reasoning-five-jds-20261013`, GPT-5.4/high trên enriched profile; không sinh Review mới. Conversation history riêng là diagnostic fixture, không lấy output mới để xây condition tiếp theo.

| Scenario | JD | Task | Vai trò |
|---|---|---|---|
| S1 | JD05 | MAS291 confidence intervals/regression và từng assessment | Known attribution regression |
| S2 | JD11 | CSI106 representation/networking và liên hệ backend | Broad foundation explanation |
| S3 | JD01 | CPV301 Object Detection/Face/Tracking và learning verbs | Interpretation boundary |
| S4 | JD11 | MAD101 C programming tools/Maxima, examples và personal use | **New holdout** |
| S5 | JD05 | Summary đa chủ đề với một CI attribution sai | Exact contaminated RCA history |
| S6 | JD05 | Summary MAS291/CLO5–9 | Same-course compression/invention |
| S7 | JD11 | Summary hẹp sorting/hashing | Former CSD holdout, now development |
| S8 | JD07 | Full JD academic synthesis, history chỉ AIL303m/CLO3 | **New holdout** |

MAD101 là nhiệm vụ metadata mới; không gọi lại ADY/DAP/PFP tools bằng schema mới rồi xem là unseen. S8 là câu hỏi tổng hợp JD07 với history outliers mới. JD07 và Review đã tồn tại trong benchmark cũ; “holdout” ở đây là scenario không dùng để thiết kế/tuning prototype, không có nghĩa JD/model chưa bao giờ gặp các topics này.

| Phase | Conditions | Generation |
|---|---|---:|
| Primary | S1–S8, A/B, S0 | 16 |
| Summary scope | S5–S8, A/B, S1 | 8 |
| Repetitions | S1/S5/S6/S8, A/B, S0; lặp một lần | 8 |
| Tổng | Unique predetermined operation IDs | **32** |

Thứ tự A/B và B/A luân phiên giữa các cặp. Repetitions giữ input/prompt/schema/settings giống originals; không chọn output tốt nhất. Holdout outputs không được dùng tuning, không thay scenario sau failure.

S0 giữ nguyên summary rules hiện có. S1 thêm cùng một block cho A/B: conversation summary chỉ giữ topics đã trao đổi, có thể lấy canonical details để sửa nguồn; comprehensive JD summary được dùng full profile/Review và thêm facts liên quan có nguồn. Một fact đúng nhưng ngoài conversation scope được phân biệt với hallucination.

B prompt chỉ thay contract/structure instructions, gồm source excerpt và duplicate policy. [prompt_contract.diff](../data/academic_grounding_prototype/prompt_contract.diff) lưu diff nguyên văn. Representation/schema và instructions cần thiết không thể được cô lập hoàn toàn; S1 là intervention riêng, không cấp cho B một summary rule chặt hơn A trong cùng cặp.

## D. Results

### Primary eight-scenario comparison

`—` nghĩa là không có public text để chấm semantic, không phải zero errors.

| Scenario | A raw P0 | B raw P0 | B gate | Requested scope | Main finding |
|---|---:|---:|---|---|---|
| S1 | 0 | 0 | pass | CI/regression explanation | Mapping/grades đúng ở cả hai; B có nguồn-free academic restatement trong general segment |
| S2 | 0 | 0 | pass | CSI foundation/backend link | CSI3 representation, CSI4 networking đúng; B thêm nguyên đoạn English JD thiếu chuyển ý tự nhiên |
| S3 | 0 | 0 | pass | CPV learning verbs | Implement OD/Explain face-tracking đúng; B lặp academic facts trong general segment thiếu local sources |
| S4 holdout | 0 | 0 | pass | MAD tools/examples/use/grades | C/Maxima chỉ là examples/context, không xác nhận individual use/assessment; B reuse metadata identity hợp lệ |
| S5 | 0 | 0 | pass | Conversation summary | Cả hai sửa CI→CLO7, không truyền lỗi CLO9 từ history |
| S6 | 0 | 0 | pass | MAS conversation summary | Cả hai mở rộng ngoài history; B thiếu CLT và numeric scores trong một grouped comparison |
| S7 | 0 | 0 | pass | Exactly sorting/hashing | Cả hai đúng CSD6/7, 6.06/basic, không mở rộng topics |
| S8 holdout | — | — | unavailable | Comprehensive JD07 | Cả A/B hết output budget trước public text |

### Atomic metrics và denominators

[Manual annotations](../data/academic_grounding_prototype/manual_annotations.json) giữ record cho mọi operation, mỗi atomic assertion có original span/context, nguồn model dùng, canonical support, provided sources, scope, severity và giải thích. [Findings](../data/academic_grounding_prototype/manual_review_findings.json) chứa **8 P1 findings + 5 P2 findings**, không sửa outputs trước grading.

| Metric | A | B | Tổng |
|---|---:|---:|---:|
| Planned/attempted operations | 16 | 16 | 32 |
| Completed public replies | 13 | 13 | 26 |
| Asked atoms trong replies có thể chấm | 54 | 54 | 108 |
| Asked atoms được trả lời | 54 | 53 | 107 |
| Answered atomic assertions | 306 | 369 | 675 |
| Added details/restatements/assertions | 252 | 316 | 568 |
| Completed outputs có academic P0 | 0/13 | 0/13 | 0/26 |
| Completed outputs có P1, gồm B-only binding | 1/13 | 5/13 | 6/26 |
| Completed outputs có P2 | 4/13 | 1/13 | 5/26 |
| Usable public response / mọi attempt | 12/16 | 11/16 | 23/32 |

Toàn matrix có **228 frozen asked atoms**. **120** thuộc sáu incomplete S8 và không thể chấm semantic; không gọi chúng là 120 academic omissions. Trong 108 evaluable units, omission đáng kể là **S6-CLT** ở B-S0 đầu. Numeric assessment tuples là riêng từng CLO; optional grades không bị biến thành yêu cầu bắt buộc chỉ vì evaluator muốn nhiều số hơn.

675 assertions gồm **636 direct**, **14 metadata**, **2 related**, **17 correct absence/boundary**, **6 JD assertions**. Không quan sát wrong source/score/band, named-framework invention, professional-experience inference hoặc personal-tool-use inference trong public text. Đây là descriptive manual counts với granularity theo từng topic/source clause và assessment tuple; không phải production error rate hoặc 675 independent statistical trials.

**279 assertions đúng về học thuật nhưng ngoài conversation scope** nằm trong ba expanded S6 outputs. Chúng được tách khỏi hallucination. `raw_semantically_correct` trong annotations chỉ đo academic factual support; `scope_correct`, `local_segment_binding_complete`, `completeness` và `usable_response` đo các yêu cầu khác. Không đồng nhất true facts với một reply đạt toàn bộ yêu cầu.

### Gate effectiveness

| Gate measure | Observed |
|---|---:|
| B attempts / output có schema để kiểm | 16 / 13 |
| Identity/literal provenance passed | 13/13 |
| Academic / JD quotes checked | 93 / 1 |
| Valid quotes | 94/94 |
| Internal repeated source uses accepted | 5 |
| Withheld by gate | 0 |
| True rejection / wrong-quote opportunity | 0 / 0 — sensitivity không thể ước lượng |
| False rejection / valid outputs | 0/13 |
| Accepted outputs có academic P0 | 0/13 |
| Accepted B outputs vi phạm local binding | 3/13 |

Gate confusion matrix về **literal provenance** và **academic factual truth** có 13 true acceptances; không có observed false academic-fact acceptance. Tuy nhiên, **9 local binding omissions**, scope expansion và requested-content omission vẫn pass gate. Các lỗi này không biến thành false academic facts, nhưng cho thấy gate không kiểm response correctness toàn diện. Software mock counterexamples cũng xác nhận quote thật có thể gắn với claim sai hoặc grade sai mà pass; không tính những mock fixtures là live findings.

Trong S4 B, cùng MAD101/tools excerpt được dùng cho listing và `not_evidenced`; aggregate external evidence chỉ giữ identity một lần. Repetition B-S6 dùng lại hợp lệ vài CLOs qua nhiều đoạn. Không có duplicate-policy false rejection như RCA AB-S2.

### Summary-scope ablation và repetitions

| Scenario | A-S0 | B-S0 | A-S1 | B-S1 |
|---|---|---|---|---|
| S5 contaminated history | CI7 đúng | CI7 đúng | CI7 đúng | CI7 đúng |
| S6 same-course history | Expanded beyond history | Expanded; CLT omitted | MAS-only, essential topics đủ | MAS-only, essential topics đủ |
| S7 explicit narrow summary | Đúng scope | Đúng scope | Đúng scope | Đúng scope |
| S8 full-JD summary | Incomplete | Incomplete | Incomplete | Incomplete |

Repetitions S0: S1/S5 vẫn giữ đúng sources/grades; B-S1 repetition vẫn có source-free general paragraph. S6 **A repetition giữ scope**, **B repetition vẫn mở rộng** sang data/ML/Python/SQL/math. Không chọn kết quả tốt nhất. S8 repeat cả hai tiếp tục incomplete.

Ở S6, history chỉ chứa MAS291/CLO5–9; data-analysis/SQL/ML curriculum từ Review/profile là academically supported additions nhưng không thuộc yêu cầu conversation summary đã freeze. Câu S0 diễn đạt tổng quát hơn “chỉ history”, nên đây là scope-boundary finding theo protocol, không khẳng định mọi generic summary người dùng đều phải hiểu cùng một cách. S7 đã nói rõ “đúng hai nội dung”, giúp cả S0/S1 tránh expansion. Không suy rằng mọi gain là do schema B.

### Naturalness và completeness

A và B nhìn chung dùng Vietnamese tự nhiên, giữ source IDs/technical terms cần thiết. Joining `"\n\n"` không thêm/sửa claims và các paragraph B vẫn đọc được; không phát hiện text bị renderer biến đổi. P2 ở A là redundant summary/source-selection offers; P2 B-S2 là standalone English JD paragraph. Không chấm reply kém chỉ vì dài hoặc nhiều CLOs: các expanded S6 bị P1 vì scope, không vì word count.

B-S6 đầu dùng band-only grouped comparison PFP191/CLO1–6; bands đều excellent thật, refs đều có, nhưng thiếu individual numeric scores theo rule comparison đã freeze. Đây là completeness/interpretation P1; không gán wrong grade. B-only source-free general segments cũng không bị đánh thành missing **aggregate** references: full external refs vẫn đúng. Ba B contract violations được tách khỏi shared academic rubric khi so A/B.

### Every attempted output, preserved original

| Raw trace | Completion | B gate | P0/P1/P2 | Public usable |
|---|---|---|---|---|
| [primary-S1-A-S0](../data/academic_grounding_prototype/live/requests/primary-S1-A-S0.json) | completed | — | 0/0/0 | yes |
| [primary-S1-B-S0](../data/academic_grounding_prototype/live/requests/primary-S1-B-S0.json) | completed | pass | 0/1/0 | yes |
| [primary-S2-B-S0](../data/academic_grounding_prototype/live/requests/primary-S2-B-S0.json) | completed | pass | 0/0/1 | yes |
| [primary-S2-A-S0](../data/academic_grounding_prototype/live/requests/primary-S2-A-S0.json) | completed | — | 0/0/0 | yes |
| [primary-S3-A-S0](../data/academic_grounding_prototype/live/requests/primary-S3-A-S0.json) | completed | — | 0/0/0 | yes |
| [primary-S3-B-S0](../data/academic_grounding_prototype/live/requests/primary-S3-B-S0.json) | completed | pass | 0/1/0 | yes |
| [primary-S5-B-S0](../data/academic_grounding_prototype/live/requests/primary-S5-B-S0.json) | completed | pass | 0/0/0 | yes |
| [primary-S5-A-S0](../data/academic_grounding_prototype/live/requests/primary-S5-A-S0.json) | completed | — | 0/0/0 | yes |
| [primary-S6-A-S0](../data/academic_grounding_prototype/live/requests/primary-S6-A-S0.json) | completed | — | 0/1/0 | no |
| [primary-S6-B-S0](../data/academic_grounding_prototype/live/requests/primary-S6-B-S0.json) | completed | pass | 0/3/0 | no |
| [primary-S7-B-S0](../data/academic_grounding_prototype/live/requests/primary-S7-B-S0.json) | completed | pass | 0/0/0 | yes |
| [primary-S7-A-S0](../data/academic_grounding_prototype/live/requests/primary-S7-A-S0.json) | completed | — | 0/0/0 | yes |
| [primary-S4-A-S0](../data/academic_grounding_prototype/live/requests/primary-S4-A-S0.json) | completed | — | 0/0/1 | yes |
| [primary-S4-B-S0](../data/academic_grounding_prototype/live/requests/primary-S4-B-S0.json) | completed | pass | 0/0/0 | yes |
| [primary-S8-B-S0](../data/academic_grounding_prototype/live/requests/primary-S8-B-S0.json) | incomplete | — | N/A | no |
| [primary-S8-A-S0](../data/academic_grounding_prototype/live/requests/primary-S8-A-S0.json) | incomplete | — | N/A | no |
| [scope-S5-A-S1](../data/academic_grounding_prototype/live/requests/scope-S5-A-S1.json) | completed | — | 0/0/1 | yes |
| [scope-S5-B-S1](../data/academic_grounding_prototype/live/requests/scope-S5-B-S1.json) | completed | pass | 0/0/0 | yes |
| [scope-S6-B-S1](../data/academic_grounding_prototype/live/requests/scope-S6-B-S1.json) | completed | pass | 0/0/0 | yes |
| [scope-S6-A-S1](../data/academic_grounding_prototype/live/requests/scope-S6-A-S1.json) | completed | — | 0/0/0 | yes |
| [scope-S7-A-S1](../data/academic_grounding_prototype/live/requests/scope-S7-A-S1.json) | completed | — | 0/0/0 | yes |
| [scope-S7-B-S1](../data/academic_grounding_prototype/live/requests/scope-S7-B-S1.json) | completed | pass | 0/0/0 | yes |
| [scope-S8-B-S1](../data/academic_grounding_prototype/live/requests/scope-S8-B-S1.json) | incomplete | — | N/A | no |
| [scope-S8-A-S1](../data/academic_grounding_prototype/live/requests/scope-S8-A-S1.json) | incomplete | — | N/A | no |
| [repeat-S1-A-S0](../data/academic_grounding_prototype/live/requests/repeat-S1-A-S0.json) | completed | — | 0/0/0 | yes |
| [repeat-S1-B-S0](../data/academic_grounding_prototype/live/requests/repeat-S1-B-S0.json) | completed | pass | 0/1/0 | yes |
| [repeat-S5-B-S0](../data/academic_grounding_prototype/live/requests/repeat-S5-B-S0.json) | completed | pass | 0/0/0 | yes |
| [repeat-S5-A-S0](../data/academic_grounding_prototype/live/requests/repeat-S5-A-S0.json) | completed | — | 0/0/1 | yes |
| [repeat-S6-A-S0](../data/academic_grounding_prototype/live/requests/repeat-S6-A-S0.json) | completed | — | 0/0/1 | yes |
| [repeat-S6-B-S0](../data/academic_grounding_prototype/live/requests/repeat-S6-B-S0.json) | completed | pass | 0/1/0 | no |
| [repeat-S8-B-S0](../data/academic_grounding_prototype/live/requests/repeat-S8-B-S0.json) | incomplete | — | N/A | no |
| [repeat-S8-A-S0](../data/academic_grounding_prototype/live/requests/repeat-S8-A-S0.json) | incomplete | — | N/A | no |

## E. Root Cause Implications

[Forensic input records](../data/academic_grounding_prototype/forensic_findings.json) kiểm raw requests/responses của ba five-JD P0 và RCA AB-S2/E2-D2/E3/E5/D-S7-D2, không lấy labels báo cáo cũ làm truth. Metadata/CLO source values, actual history và Review đều có trong artifacts.

- **Finding/source identification:** current nonfailed examples locate MAS7/9, CSI3/4 và CPV8/9 đúng ở cả A/B. Không có retrieval intervention nên không chứng minh retrieval là nguyên nhân hoặc đã được giải quyết.
- **Representation/claim correspondence:** B loại independent final-reply generation của D2 theo thiết kế, nhưng general segment vẫn có thể mang positive facts không local sources. Đây là observed escape path; không chứng minh hidden reasoning hoặc production schema là nguyên nhân duy nhất.
- **History authority:** cả sáu completed S5 outputs giữ CI→MAS7, thay attribution CLO9 có trong seeded history. Đây là evidence trái chiều với việc coi contamination luôn sẽ propagate; không sửa original history fixture/session.
- **Summary synthesis:** S6 vẫn mở rộng khỏi actual history, nhưng current added academic sources đúng. S1 hỗ trợ scope ở cả paths. A repetition khác lần đầu cho thấy variability; observed pair không đủ causal proof.
- **Completion:** broad S8 thất bại ở cả representations. Usage metadata chỉ cho thấy reasoning/output ceiling bị dùng hết; không cho biết model đã tìm nguồn hay suy nghĩ theo cơ chế nào.

Không gọi current study là “đã sửa ba P0 RCA”. Các probes/questions, output contracts và controls khác lịch sử; không có current A P0 để đo một error-reduction effect của B.

## F. Generalization

Holdout MAD101 mới vượt factual/source/tool-choice boundaries ở cả A/B. Điều này cung cấp một successful generalization example ngoài MAS291/CSI106, gồm metadata-only grounding và repeated identity.

**Holdout comprehensive JD07 chưa được kiểm semantic:** 0/6 có text. Không có dữ liệu để nói S1 giữ đúng comprehensive scope mà không bỏ legitimate new facts, hoặc B tổng hợp tốt full JD. JD07/Review đã tồn tại lịch sử; chỉ scenario/history/probe là holdout khỏi prototype development, không phải course/JD hoàn toàn chưa từng xuất hiện.

PFP/CSD RCA holdouts không được gọi unseen trong study này. S7 CSD đã thành development example. Không tuning prompt/schema, thay holdout hoặc regenerate sau khi thấy failure.

## G. Engineering Tradeoffs

### Usage và costs

Giá rechecked từ [OpenAI Docs — GPT-5.4 Mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini) trước live: input **0,75**, cached input **0,075**, output **4,50 USD/triệu tokens**. Reasoning nằm trong output, cache là subset của input; không tính hai lần.

| Usage | A, 16 requests | B, 16 requests | Tổng |
|---|---:|---:|---:|
| Input tokens | 324.237 | 330.045 | 654.282 |
| Cached input | 267.008 | 265.728 | 532.736 |
| Output tokens, gồm reasoning | 36.165 | 49.041 | 85.206 |
| Reasoning tokens | 30.867 | 40.204 | 71.071 |
| Known cost USD | 0,22568985 | 0,28885185 | **0,51454170** |
| Unknown reservation USD | 0 | 0 | **0** |

B có **+363 input tokens ở mọi matched pair** do contract/schema overhead; không khác profile/JD/history. Completed output mean/median A **891,46/763**, B **1.881,92/813** tokens; B fat tail chủ yếu ở long expanded S6, thêm internal quotes và reasoning. Observed B cost cao hơn A khoảng **28%**, không suy đây là production cost multiplier cố định.

Peak preflight input **20.994** + output reserve **8.192** thấp hơn context **400.000**; không có truncation/context overflow. Sáu S8 tiêu thụ tổng **49.152 reasoning/output tokens**, không có public text. Timeout **0/32**, incomplete **6/32=18,75%**, refusal/parser/API failure **0**. Mọi requested/resolved model đúng snapshot; temperature omitted, retries=0.

### Latency, mean / median giây

| Measurement | A | B | Denominator |
|---|---|---|---|
| Preflight HTTP | 0,750 / 0,710 | 0,705 / 0,609 | 16 mỗi arm |
| Generation HTTP/body, all attempts | 10,944 / 4,601 | 13,880 / 6,285 | 16 mỗi arm |
| SDK parsing | 0,00871 / 0,00111 | 0,00129 / 0,00121 | 16 mỗi arm |
| Local validation/adapter | 0,01002 / 0,00943 | 0,01976 / 0,01911 | 13 completed mỗi arm |
| Total operation, all attempts | 11,938 / 5,564 | 14,810 / 7,368 | 16 mỗi arm |
| Generation HTTP, completed only | 4,949 / 4,319 | 8,703 / 4,749 | 13 mỗi arm |
| Total, completed only | 5,979 / 5,213 | 9,656 / 5,566 | 13 mỗi arm |

Validation/adapter gồm local artifact writes; total gồm preflight, source checks và recording. First schema/SDK parse warmup, cache/order và stochastic output length là confounds; không quy mọi latency difference cho gate. Không thay những missing validation measurements ở S8 thành zero.

Ledger lưu counters/reservations trước dispatch, dùng full context và output reserve thực. [run.json](../data/academic_grounding_prototype/live/run.json), [usage.json](../data/academic_grounding_prototype/live/usage.json) và traces giữ mọi failure. Không resume/regenerate condition hoặc dùng output mới làm input. No successful output/session được tạo cho S8.

### Integrity và checks

Plan SHA-256 không đổi:

```text
c1290e852fec45aa8aa22b1fff46e7baf4d7f44cbcf8e21e6c0ea4b9341fd5b3
```

[Plan](../data/academic_grounding_prototype/plan.json), [approval](../data/academic_grounding_prototype/live_authorization.json), prompts/schemas/questions/source order/expected evidence không đổi. **39 source files + 10 frozen artifacts + plan = 50 execution fingerprints** còn nguyên. **1.451 preexisting files** và **110 original request/parsed/raw-view/gate/public-output artifacts** giữ hashes trước–sau grading. Source prompts/schemas/defaults/data/.env/historical annotations và production sessions giữ nguyên.

675 original claim spans/source memberships đã kiểm consistency; semantic support vẫn do reviewer đọc source/history, không suy từ identity check. Post-inference manual extraction/analysis không được inference runner import hoặc dùng tuning.

## H. Recommendation

**Chọn 2: chỉ cân nhắc explicit summary-scope clarification trong một task production riêng. Giữ current external schema và sessions; chưa adopt B.** Scope clarification là thay đổi nhỏ nhất có observed benefit ở cả arms, nhưng vẫn cần regression/comprehensive-summary validation tiếp. Task này không triển khai grounding fix hoặc đổi production prompt/defaults.

| Research question | Observed evidence | Interpretation / uncertainty |
|---|---|---|
| 1. B giảm raw semantic grounding errors? | A/B đều 0/13 observed academic P0 | **Inconclusive**; control không có P0 để đo reduction |
| 2. Chủ yếu prevention hay detectability? | Không wrong-quote opportunity, không gate reject | Chưa phân biệt được; richer artifacts giúp inspection, không phải measured error prevention |
| 3. Gate chặn genuinely wrong associations? | Mock checks reject sai quote/ID; live không có loại lỗi đó | Software behavior verified, live sensitivity chưa ước lượng |
| 4. Reject semantically correct replies? | 0/13 B rejected; legitimate repeated sources pass | Không false rejection quan sát; sample nhỏ |
| 5. Sai semantics có thể pass quote gate? | Mock counterexample pass; live pass dù 9 local-binding faults và scope/omission | Gate không entailment/closure/scope validator; live không observed false academic fact |
| 6. S1 giảm invented/unnecessary topics? | S6-S1 MAS-only cả A/B; S0 có expansions | Hỗ trợ scope benefit; additions S0 đúng về học thuật, không gọi hallucination |
| 7. Scope gain độc lập representation? | Benefit xuất hiện cả A/B | Hỗ trợ xử lý như separate intervention; không causal guarantee từ một pair |
| 8. B thêm omission/unnaturalness? | CLT omitted một output, conditional numeric omission; English block và source-free facts | Tradeoffs thật; không impose arbitrary brevity/segment count |
| 9. Beyond MAS/CSI generalization? | MAD tools holdout đúng; full JD07 0/6 text | Một successful new case, broad synthesis chưa được đánh giá |
| 10. Complexity có đáng cho V1? | B chưa có factual advantage, cost/latency tăng, local-binding loophole | **Chưa đủ bằng chứng adoption**; smaller scope rule đáng thử trước |

Follow-up cần thiết, không chạy trong budget này: kiểm completion của broad JD summary với output/effort phù hợp trong study mới; kiểm S1 trên nhiều explicit/ambiguous conversation và comprehensive requests; nếu tiếp tục B, đo kind misclassification/closure trên holdouts mới. Chưa khuyến nghị tăng ceiling/giảm effort như production default vì chưa có controlled evidence về semantic tradeoff.

Classroom MVP có thể dùng kết quả để giới hạn kỳ vọng của prototype; không tuyên bố grounding toàn pipeline được nghiệm thu chỉ vì 26 outputs parse hợp lệ hoặc không có P0 quan sát. Full-JD summary failure và scope/contract problems còn là material limitations.

## I. Limitations

32 lượt là selected diagnostic sample; 26 replies và 13 gate-assessable B outputs không đại diện mọi 15 JD. Không có current P0-positive controls; detection sensitivity và raw P0 improvement chưa đo được. Hai holdouts chỉ có một có public output. Repetitions ít, paired outputs phụ thuộc shared model/input và stochastic/cache effects.

Manual atomic counts phụ thuộc granularity, source-clause interpretation và subjectivity; additional restatements/details không được completion credit. Correct source quotes không tự chứng minh claim entails; correct academic facts không tự xác nhận scope/completeness/local correspondence. Grade bands đúng nhưng thiếu score trong conditional comparison được ghi P1 riêng, không thành invented score.

B đổi representation, schema/field order và necessary contract instructions cùng lúc. S1 là explicit shared scope intervention, không artificial weakening S0. S6 generic summary wording có interpretation boundary; cần kiểm robust ngoài một case. No hidden reasoning inspected; reasoning-token counters không cho phép kết luận về cơ chế bên trong.

Zero published P0 ở đây luôn đi kèm **26 published, 0 gate-withheld, 6 incomplete no-reply**; end-to-end usable **23/32**, không phải “32/32 an toàn và đủ”. Không sửa bất kỳ model output, canonical grade hoặc historical annotation để đạt kết quả tốt hơn.
