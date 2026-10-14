# Kiểm định CLO Enrichment toàn bộ Stage 3 — SkillBridge

> Phạm vi: `/mnt/data/stage3.zip`, gồm 49 thư mục môn và 346 CLO. Kiểm định không sửa dữ liệu gốc.

## Kết luận

**Chưa đạt để đưa toàn bộ enrichment vào production; chưa nên rút gọn thành `clo` + `description` trên tập hiện tại.** Khung JSON đã đúng, nhưng tồn tại các lỗi có thể gây sai kết quả JD matching. Các CLO được viết tốt nên giữ nguyên (ví dụ DBI202/CLO5, CSD203/CLO5, AIM301m/CLO5, PFP191/CLO5).

## 1. Độ đầy đủ và hợp lệ

| Kiểm tra | Kết quả |
|---|---:|
| Thư mục môn / output | 49 / 49 |
| Thư mục có CLO | 48 |
| Thư mục không có CLO (`AI17_GRA_ELE`) | 1 |
| CLO gốc / CLO enrich | 346 / 346 |
| Lỗi JSON/schema/course_id/ID trùng/thứ tự/bằng chứng index | 0 |
| Source descriptions không khớp bản gốc | 0 |
| CLO có `review_required: true` | 0 |
| Enriched CLO dạng `The scope includes...` | 308 / 346 |

Nguồn mâu thuẫn: báo cáo cũ của Codex nói không còn marker hành chính, nhưng ít nhất một số output chứa `Welcome to...`, `Lab 4 assistant and interview`, `Guest speaker`, `Review Report`, v.v.

## 2. Bộ lọc trên toàn bộ 346 CLO (chỉ là dấu hiệu cần xem lại)

| Dấu hiệu tự động | Số CLO |
|---|---:|
| Nhãn buổi học/hành chính còn trong mô tả | 14 |
| Bình luận meta về CLO thay vì outcome | 5 |
| Từ/cụm từ bị xử lý sai hoặc chép typo trực tiếp | 3 |
| `The scope includes...` dài trên 90 từ | 21 |
| CLO gốc có sub-LO nhưng bản enrich rút ngắn mạnh, cần kiểm tra thiếu ý | 17 |
| Tổng số CLO được xếp vào queue (gộp, không đếm lặp) | 56 |

Các nhóm có thể giao nhau; không được hiểu số liệu trên là số lỗi ngữ nghĩa đã được chứng minh. Ví dụ MAS291 có CLO được rút gọn nhưng vẫn giữ các nội dung quan trọng.

## 3. Những lỗi/rủi ro xác minh thủ công qua CLO gốc và topics

| Môn/CLO | Ưu tiên | Phát hiện |
|---|---|---|
| `SEG301/CLO3` | **P0** | Keyword research bị biến thành web crawling, index construction và document storage; cần kiểm tra topic mapping. |
| `SEG301/CLO4` | **P0** | Website analytics/tracking bị mở rộng sang inverted indexes, BM25 và clustering; sai scope rất rõ. |
| `NLP301m/CLO7` | **P0** | Responsible AI-assisted tooling bị trộn với reports/literature review; không có bằng chứng topic tương ứng rõ ràng. |
| `MAD101/CLO1` | **P1** | Mất propositional logic, predicate logic và equivalence trong sub-LO dù nằm trong CLO gốc. |
| `MAD101/CLO8` | **P1** | Mất Huffman, BST, DFS/BFS, Prim, Kruskal; chuyển thành tên chương học chung. |
| `MAE101/CLO1` | **P1** | Mất Squeeze Theorem, asymptotes, continuity và Intermediate Value Theorem. |
| `MAE101/CLO4` | **P1** | Mất Fundamental Theorem, Riemann sum, Simpson, phương pháp xấp xỉ số. |
| `CPV301/CLO6` | **P1** | Lỗi text 2D thành "D and 3D". |
| `CPV301/CLO7` | **P1** | Bỏ Global alignment; lại giữ "Lab 4 assistant and interview". |
| `TMG301/CLO1` | **P1** | Phạm vi fundamentals trải từ Word2Vec đến Transformers, dịch máy, dialogue... Cần đánh giá overmatching. |
| `GAP301/CLO1` | **P2** | Lẫn logistics và hình thức tổ chức nhóm vào mục tiêu học thuật. |
| `TMG301/CLO3` | **P2** | Đưa bình luận về dữ liệu ("The CLO itself names...") vào mô tả cho JD matching. |

**P0**: Mismatch ngữ nghĩa khiến JD matching suy ra sai domain; cần xác minh `topics_by_clo.json` trước khi enrich.  **P1**: Mất kỹ thuật rõ ràng trong nguồn, hoặc làm hỏng thuật ngữ.  **P2**: Nhiễu diễn đạt, nhãn hành chính hoặc cấu trúc không tự nhiên.

## 4. Các ví dụ đối chiếu cụ thể

### `SEG301/CLO4` — Mismatch nguồn

- **CLO gốc:** Tracking website traffic, user behavior, campaign performance.
- **Bản enrich:** Thêm inverted indexes, BM25, Naive Bayes, SVM và clustering.
- **Đánh giá:** Những topic này có trong file `topics_by_clo.json`, nhưng không liên quan trực tiếp đến mục tiêu CLO được giao. Không nên cố ép chúng vào mô tả. Cần kiểm tra lại mapping hoặc giữ nguyên CLO gốc và đánh dấu cần rà soát.

### `CPV301/CLO7` — Mất nội dung hữu ích, giữ nội dung hành chính

- **Topic thực sự liên quan:** `Image stitching / Motion models` (index 0) và `Image stitching / Global alignment` (index 1).
- **Codex đã chọn:** indices `[0, 2]`, trong đó index 2 là `Lab 4 assistant and interview`.
- **Gợi ý mô tả:** `Discuss the principles and implementation of image stitching, including motion models and global alignment.`

### `MAD101/CLO8` — Mất kỹ thuật cụ thể

- **CLO gốc ghi rõ:** Binary search trees, decision trees, Huffman coding, DFS/BFS, Prim/Kruskal.
- **Bản enrich:** Chỉ liệt kê tên chương Introduction to Trees, Applications of Trees, Tree Traversal, Spanning Trees, Minimum Spanning Trees.
- **Đánh giá:** Mất nhiều bằng chứng hữu ích cho JD matching dù đã tồn tại trực tiếp trong CLO gốc.

### Ví dụ hợp lý có thể giữ nguyên

- `DBI202/CLO5`: DDL, constraints, nested queries, aggregation, DML được kết hợp rõ và có nguồn.
- `CSD203/CLO5`: Edge/adjacency representations, traversal, Dijkstra, Prim/Kruskal được cụ thể hóa.
- `PFP191/CLO5`: File handling trong Python được khai triển thành thao tác rõ ràng mà không tăng cognitive level.

## 5. Khuyến nghị xử lý

1. Giữ output `enriched_clos.json` hiện tại làm **audit backup**, không ghi đè nguồn `clos.json` hoặc `topics_by_clo.json`.
2. Sửa các CLO P0 trước. Nếu mapped topics không phù hợp, không cố hợp thức hóa: giữ CLO gốc, flag mapping conflict và yêu cầu người dùng xác nhận.
3. Viết lại ở cấp CLO bằng suy luận ngữ nghĩa từ *tất cả CLO cùng môn*, không chỉ cắt ghép tên topic. Bảo toàn các technical terms vốn đã có trong các sub-LO gốc.
4. Chỉ giữ thuật ngữ mới được hỗ trợ; loại đầu mục chương, giờ học, welcome, progress/lab/report labels và bình luận về quá trình phân tích.
5. Chạy QA lại trên toàn bộ 346 CLO và review thủ công ít nhất các P0/P1 cùng các CLO có đặc điểm bất thường.
6. **Chỉ khi QA đạt**, tạo bản production tách riêng, cấu trúc `[ {"clo":"CLO1", "description":"..."} ]`, đồng thời giữ full audit JSON trong kho riêng để truy vết.

## 6. Giới hạn kiểm định

- Toàn bộ 346 CLO đã được kiểm định cấu trúc và chạy các bộ lọc văn bản tự động.
- Các lỗi P0/P1/P2 nêu trong bảng đã được đối chiếu thủ công với CLO và topic liên quan; **không phải mọi CLO ngoài bảng đều đã được xác nhận đúng về ngữ nghĩa**.
- Bộ lọc tự động không phát hiện được mọi lỗi overclaim, thiếu kỹ thuật hay mapping sai; `review_required: false` của output gốc không phải giấy chứng nhận chất lượng.
- Bản audit này không tính accuracy % vì chưa có gold labels hay rubric đánh giá có kiểm định.

## 7. Files

- `clo_enrichment_review_queue.json`: Các bản ghi có dấu hiệu cần kiểm tra (có phân biệt phát hiện thủ công và heuristic).
- `codex_clo_revision_prompt.md`: Prompt để Codex sửa trước khi rút gọn production schema.
