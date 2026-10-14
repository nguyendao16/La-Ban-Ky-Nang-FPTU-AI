# Báo cáo hoàn tất CLO Enrichment Stage 3

Ngày chạy: 2026-10-12

## Tổng quan

- Phạm vi xử lý: toàn bộ `data/stage3/`.
- Số course directory: 49.
- Số course có CLO: 48.
- Course không có CLO: `AI17_GRA_ELE`.
- Tổng số CLO đối chiếu từ `clos.json`: 346.
- Tổng số `enriched_clos.json` production sau migration: 49.
- Tổng số enriched CLO production: 346.

## Backup và audit

- Backup trước Phase 3: `docs/clo_enrichment_qa_package/backups/pre_phase3_full_revision_20261012_200110/`.
- Detailed audit backup trước khi compact schema: `docs/clo_enrichment_qa_package/backups/phase3_detailed_audit_20261012_200751/`.
- Detailed change log: `docs/clo_enrichment_qa_package/phase3_detailed_change_log.json`.
- Số detailed records thay đổi trong Phase 3: 298.

## Validation

- Structural validation trước schema migration: pass.
- Production schema validation sau migration: pass.
- Course count: 49 / 49.
- CLO count: 346 / 346.
- `AI17_GRA_ELE`: giữ production JSON là `[]`.
- Root schema production: list JSON.
- Record schema production: đúng hai field `clo` và `description`.
- CLO ID và thứ tự: khớp `clos.json`.
- Description rỗng: 0.
- Duplicate CLO ID: 0.
- Marker hành chính/meta còn trong production description: 0.
- Cụm thuật ngữ hỏng đã kiểm tra: 0.
- `clos.json` và `topics_by_clo.json`: không sửa.

## Downstream compatibility

Đã kiểm tra bằng `rg` ngoài `data/stage3/` và ngoài package QA docs; không thấy code production đọc trực tiếp `enriched_clos.json`. Do đó migration schema gọn không yêu cầu sửa consumer code hiện tại. Pipeline skill extraction hiện có vẫn dùng các nguồn khác như `clos.json` hoặc `clo_skills.json`.

## Manual-review flags còn lại trong detailed audit

Các issue dưới đây không còn làm production description sai scope; production giữ mô tả faithful từ CLO gốc. Detailed audit vẫn flag để truy vết mapping/source không đủ chắc:

| Course/CLO | Lý do |
|---|---|
| `DSR301m/CLO6` | Topics là assignment/review/grading labels, không phải topic kỹ năng project cụ thể. |
| `EXE101/CLO2` | Topic là guest-speaker seminar, không trực tiếp support team-building competency. |
| `MAI391/CLO8` | Topics là review/progress/presentation logistics, không trực tiếp support soft-skill CLO. |
| `NLP301m/CLO7` | Mapped topics là research project/report stages, không trực tiếp support responsible AI-assisted development tools. |
| `SEG301/CLO3` | Mapped topics không trực tiếp support practical keyword research proficiency. |
| `SEG301/CLO4` | Mapped topics lệch sang indexing/retrieval/classification/clustering thay vì analytics tracking. |

Ghi chú: `CMO301m` có 5 CLO không có mapped topics do lỗi nguồn nhà trường đã được xác nhận có thể bỏ qua; production descriptions dựa trên CLO gốc giàu chi tiết, không invent thêm từ topic rỗng.

## Ví dụ production JSON cuối

`data/stage3/DBI202/enriched_clos.json`

```json
[
  {
    "clo": "CLO1",
    "description": "Understand core database concepts and database management system software, including the evolution of database systems, the role and overview of DBMS software, and the major areas studied in database systems."
  },
  {
    "clo": "CLO2",
    "description": "Understand the relational model of data, including general data model concepts and the basic structure of relations. Explain the purpose of algebraic query language in expressing relational operations and reasoning about queries at a conceptual level."
  }
]
```

`data/stage3/SEG301/enriched_clos.json`

```json
[
  {
    "clo": "CLO1",
    "description": "Explain how search engines work, including information retrieval and web search concepts, search engine architecture, crawling and document acquisition, text processing, inverted indexes and index construction, query processing, and ranking with Boolean, proximity, vector-space, probabilistic, BM25, language-model, and learning-to-rank retrieval models."
  },
  {
    "clo": "CLO2",
    "description": "Apply SEO best practices to improve search engine results page visibility, including content quality, site architecture, HTML factors, trust, links, user-related factors, spam and ranking updates, special collections, and the role of search engine providers."
  }
]
```

`data/stage3/AI17_GRA_ELE/enriched_clos.json`

```json
[]
```

## Kết luận

Phase 3 semantic repair và Phase 4 production schema migration đã hoàn tất. Các unresolved mapping issues còn lại đã được giữ trong detailed audit backup, không bị đưa thành unsupported competency trong production descriptions.
