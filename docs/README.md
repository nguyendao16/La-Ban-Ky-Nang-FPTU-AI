# Tài liệu dự án La Bàn Kỹ Năng

Thư mục tài liệu kỹ thuật, kiến trúc và quyết định thiết kế của hệ thống La Bàn Kỹ Năng.

## Hướng dẫn vận hành và thử nghiệm

- [Kiến trúc hệ thống](architecture.md): Tổng quan kiến trúc hiện hành, biên giới dữ liệu, hàng đợi tác vụ nền, cơ chế đối chiếu CWA/JD và radar 5 trục.
- [Hướng dẫn chạy live](live_guide.md): Hướng dẫn khởi chạy môi trường live 3 tiến trình (API, background worker, frontend), cấu hình biến môi trường và xử lý sự cố vận hành.
- [Cache kết quả demo](demo_cache.vi.md): Cấu hình và cơ chế cache kết quả server-side cho kịch bản demo Data Analyst và JD AI Engineer Intern.
- [Kịch bản demo](demo_script.vi.md): Kịch bản trình diễn luồng đối chiếu môn học với nhóm nghề CWA và JD, hỏi đáp Chat và gợi ý Coursera.

## Quyết định kiến trúc (Architecture Decision Records)

- [ADR 0001: Sử dụng nhóm nghề CWA được cung cấp](adr/0001-use-provided-cwa-career-groups.md)
- [ADR 0002: Cố định hồ sơ nhóm nghề trong snapshot phiên](adr/0002-pin-career-target-in-session.md)
- [ADR 0003: Radar năm trục do LLM xác định trong cùng lần đối chiếu](adr/0003-model-defined-career-radar.md)
- [ADR 0004: Cố định năm trục theo tám vị trí, giới hạn điểm tổng trong năm trục](adr/0004-fixed-cwa-target-axes.md)
- [ADR 0005: Một bộ gợi ý Coursera riêng cho mỗi kết quả đã lưu](adr/0005-durable-coursera-suggestions.md)

## Quy ước Agent & Tri thức lĩnh vực

- [Tri thức lĩnh vực (Domain)](agents/domain.md): Hướng dẫn sử dụng `GLOSSARY.md` và các ADR khi tìm hiểu hoặc thay đổi kiến trúc.
- [Theo dõi vấn đề (Issue tracker)](agents/issue-tracker.md): Quy ước theo dõi tác vụ và quy cách kỹ thuật cục bộ.
- [Nhãn phân loại (Triage labels)](agents/triage-labels.md): Năm vai trò phân loại mặc định.
