"""Application-owned CWA target scopes, pinned into each new career snapshot."""
from pydantic import Field, model_validator

from .models import StrictModel


class CareerAxisDefinition(StrictModel):
    name: str = Field(max_length=64)
    description: str


class CareerTarget(StrictModel):
    title: str
    scope: str
    axes: list[CareerAxisDefinition] = Field(min_length=5, max_length=5)

    @model_validator(mode='after')
    def distinct_axes(self):
        if len({axis.name.strip().casefold() for axis in self.axes}) != 5:
            raise ValueError('Career target axes must be distinct')
        return self


# These are application groupings of the supplied summaries, not official CWA axes.
TARGETS = {
    'data-scientist': (
        'Data Scientist',
        'Quy trình khoa học dữ liệu từ bài toán kinh doanh, dữ liệu và mô hình đến kết quả phân tích; gồm quản trị, bảo mật và tuân thủ dữ liệu trong nguồn.',
        (
            ('Data Preparation & Governance', 'Thu thập, làm sạch, hợp nhất và duy trì dữ liệu nhất quán; gán nhãn, đánh giá và lập kế hoạch quản lý dữ liệu; bảo mật chủ động, đạo đức và tuân thủ pháp lý dữ liệu.'),
            ('Business Problem Modelling', 'Biểu diễn thách thức kinh doanh bằng mô hình toán học, xác định mục tiêu phân tích và cách ứng dụng dữ liệu để tạo giá trị kinh doanh.'),
            ('Statistical Analysis', 'Phân tích và điều tra dữ liệu; tạo, kiểm chứng giả thuyết và phát hiện tương quan phục vụ đo lường, dự báo bằng các kỹ thuật thống kê phù hợp.'),
            ('AI/ML Modelling & Evaluation', 'Lựa chọn, ứng dụng, tối ưu và đánh giá thuật toán, mô hình AI/ML theo bài toán; xem xét thành phần mô hình và báo cáo kết quả đánh giá.'),
            ('Visualization & Communication', 'Lựa chọn trực quan hóa phù hợp bài toán và dữ liệu; trình bày kết quả phân tích, truyền đạt mô hình phát hiện được và đề xuất cách ứng dụng dữ liệu.'),
        ),
    ),
    'data-analyst': (
        'Data Analyst',
        'Phân tích và giải thích dữ liệu theo mục tiêu kinh doanh; gồm mô hình dữ liệu, chất lượng, trực quan hóa, quản trị và bảo vệ dữ liệu trong nguồn.',
        (
            ('Data Collection & Modelling', 'Thu thập, nhập và biểu diễn dữ liệu; định nghĩa, xây dựng, tối ưu mô hình dữ liệu hỗ trợ mục tiêu kinh doanh và các nguồn dữ liệu liên quan.'),
            ('Data Quality & Transformation', 'Kiểm tra, làm sạch, biến đổi, xác thực dữ liệu; đảm bảo chất lượng, tính nhất quán và toàn vẹn trên các kho lưu trữ, kể cả chất lượng tập dữ liệu AI và nhãn.'),
            ('Data Analysis & Interpretation', 'Phân tích, mô hình hóa và giải thích tập dữ liệu để nhận diện thông tin có ý nghĩa và cách dữ liệu hỗ trợ giải quyết bài toán doanh nghiệp.'),
            ('Visualization & Business Insights', 'Xây dựng biểu đồ và dashboard, trình bày và truyền đạt insights từ dữ liệu theo mục tiêu kinh doanh.'),
            ('Data Governance & Protection', 'Quản trị và lưu trữ dữ liệu để duy trì khả năng truy cập, độ tin cậy; bảo mật, riêng tư suốt vòng đời và tuân thủ pháp lý, chính sách quản trị dữ liệu.'),
        ),
    ),
    'ai-ml-engineer': (
        'Machine Learning Engineer',
        'Phần kỹ thuật AI/ML dùng chung trong hồ sơ: mô hình, thành phần, workflow và hệ thống tích hợp. Không bắt buộc chuyên môn Computer Vision hoặc NLP/LLM.',
        (
            ('AI Tooling & Workflows', 'Lựa chọn phần cứng, phần mềm, công cụ và framework AI/ML phù hợp thông số giải pháp; tổ chức workflow ML phục vụ xây dựng và thực thi hệ thống.'),
            ('Model & Component Development', 'Phát triển và kỹ thuật hóa mô hình, thành phần AI/ML theo thông số giải pháp; xem xét hiệu năng, hiệu quả và mã nguồn được lập tài liệu.'),
            ('Testing & Troubleshooting', 'Lập kế hoạch kiểm thử, kiểm tra thành phần AI/ML; chẩn đoán và xử lý sự cố trước, sau kiểm thử, cung cấp hỗ trợ kỹ thuật chuyên sâu và xem xét độ tin cậy.'),
            ('Integration & Deployment', 'Tích hợp thành phần thành giải pháp AI, xây dựng và triển khai hệ thống, quản lý đường ống triển khai; xem xét khả năng mở rộng, độ tin cậy và hiệu quả hệ thống.'),
            ('Secure & Responsible AI Engineering', 'Bảo mật từ thiết kế, xử lý lỗ hổng đã biết, an toàn và đạo đức AI; xây dựng tài liệu kỹ thuật hệ thống, gồm phạm vi AI rủi ro cao hoặc GPAI khi nguồn yêu cầu.'),
        ),
    ),
    'computer-vision-engineer': (
        'Computer Vision Engineer',
        'Phần kỹ thuật AI/ML dùng chung, áp dụng cho nhánh hình ảnh/video, phân đoạn và nhận dạng đối tượng thị giác. Không bắt buộc chuyên môn NLP/LLM.',
        (
            ('Image & Video Processing', 'Xử lý dữ liệu hình ảnh và video bằng các thuật toán thị giác phù hợp phạm vi chuyên môn hóa được nêu trong nguồn.'),
            ('Vision Model Development', 'Phát triển và kỹ thuật hóa mô hình, thành phần thị giác; bao gồm nhận dạng đối tượng và phân đoạn, theo thông số giải pháp và hiệu quả xử lý.'),
            ('Testing & Troubleshooting', 'Lập kế hoạch kiểm thử thành phần, mô hình thị giác; chẩn đoán, xử lý sự cố và hỗ trợ kỹ thuật trước, sau kiểm thử, xem xét độ tin cậy của giải pháp.'),
            ('Vision Integration & Deployment', 'Lựa chọn phần cứng, phần mềm, công cụ và framework phù hợp; tích hợp, triển khai giải pháp thị giác và quản lý workflow, đường ống triển khai, hiệu năng và khả năng mở rộng.'),
            ('Secure & Responsible Vision Engineering', 'Bảo mật từ thiết kế và xử lý lỗ hổng, an toàn, đạo đức AI trong giải pháp thị giác; mã nguồn được lập tài liệu và tài liệu kỹ thuật hệ thống theo phạm vi nguồn.'),
        ),
    ),
    'nlp-llm-engineer': (
        'NLP / LLM Engineer',
        'Phần kỹ thuật AI/ML dùng chung, áp dụng cho NLP, fine-tuning LLM, prompting và tích hợp AI tạo sinh. Không bắt buộc Computer Vision hoặc huấn luyện LLM từ đầu.',
        (
            ('Text Processing', 'Xử lý văn bản và ngôn ngữ tự nhiên trong phạm vi nhánh NLP/LLM; tổ chức thành phần xử lý ngôn ngữ phù hợp thông số giải pháp.'),
            ('Model Adaptation & Prompting', 'Tinh chỉnh mô hình ngôn ngữ lớn và Prompt Engineering để thích ứng với giải pháp; phát triển thành phần mô hình phù hợp, không tự thêm yêu cầu huấn luyện LLM từ đầu.'),
            ('NLP/LLM Testing & Troubleshooting', 'Lập kế hoạch kiểm thử và kiểm tra thành phần NLP/LLM; chẩn đoán, xử lý sự cố, hỗ trợ kỹ thuật và xem xét độ tin cậy theo phạm vi nguồn, không tự bắt buộc bộ chỉ số ngoài nguồn.'),
            ('Application Integration & Deployment', 'Lựa chọn công cụ, framework và tài nguyên phù hợp; tích hợp AI tạo sinh vào giải pháp, quản lý workflow và đường ống triển khai, khả năng mở rộng và hiệu quả hệ thống.'),
            ('Secure & Responsible AI Engineering', 'Bảo mật từ thiết kế, xử lý lỗ hổng, an toàn và đạo đức AI; mã nguồn được lập tài liệu, tài liệu kỹ thuật hệ thống theo phạm vi AI rủi ro cao hoặc GPAI trong nguồn.'),
        ),
    ),
    'mlops-engineer': (
        'MLOps Engineer',
        'Tự động hóa, triển khai và vận hành vòng đời mô hình ML trên production theo hồ sơ MLOps, gồm hạ tầng, theo dõi, khôi phục, bảo mật và tuân thủ.',
        (
            ('Model & Data Lifecycle', 'Đóng gói, quản lý phiên bản mô hình và dữ liệu, theo dõi thực nghiệm; quản lý cập nhật mô hình xuyên suốt vòng đời và chuẩn hóa quy trình hợp tác.'),
            ('Infrastructure & Scalability', 'Quản lý hạ tầng ML, cloud, container và orchestration; đảm bảo hệ thống có thể mở rộng và đáp ứng công việc ML trên production.'),
            ('Pipeline & Deployment Automation', 'Thiết kế, triển khai CI/CD cho mô hình và dữ liệu; tự động hóa workflow tạo, huấn luyện, triển khai, cập nhật và huấn luyện lại mô hình.'),
            ('Monitoring & Recovery', 'Giám sát hiệu năng mô hình, drift và sức khỏe hệ thống; duy trì nhật ký, hồ sơ vận hành và tự động hóa khôi phục, rollback trên production.'),
            ('Security & Compliance', 'Đảm bảo an ninh và tuân thủ cho hệ thống ML, xây dựng và áp dụng hướng dẫn an ninh AI/ML theo phạm vi hồ sơ.'),
        ),
    ),
    'ai-researcher': (
        'Algorithm Research Engineer',
        'Nghiên cứu thuật toán, mô hình và nền tảng lý thuyết AI/ML mới; gồm thực nghiệm, các thách thức nghiên cứu cốt lõi, công bố và tác động theo hồ sơ.',
        (
            ('Theoretical Foundations', 'Phát triển nền tảng và mô hình lý thuyết giải thích hành vi, hiệu năng hệ thống AI, trên cơ sở toán học, khoa học máy tính và kiến thức chuyên ngành.'),
            ('Algorithm & Model Innovation', 'Khám phá, thiết kế, phát triển thuật toán, mô hình và learning paradigms mới nhằm mở rộng giới hạn chuyên môn và nâng cao khả năng mô hình AI/ML.'),
            ('Scientific Experimentation', 'Thiết kế và thực hiện thực nghiệm kiểm chứng giả thuyết trên benchmark hoặc mô phỏng; thử nghiệm thuật toán, mô hình và xác thực kết quả nghiên cứu nguyên bản.'),
            ('Generalization, Interpretability & Alignment', 'Nghiên cứu khả năng tổng quát hóa, tính diễn giải và căn chỉnh an toàn; xem xét hệ thống AI an toàn, đạo đức theo các thách thức cốt lõi nêu trong nguồn.'),
            ('Research Communication & Impact', 'Truyền đạt và công bố nghiên cứu tại hội nghị, tạp chí AI; xem xét chất lượng nguyên bản, lan tỏa kết quả và đóng góp, tác động xã hội của nghiên cứu.'),
        ),
    ),
    'ai-data-platform-engineer': (
        'AI & Data Platform Engineer',
        'Giữ phạm vi kết hợp AI Platform Engineer và Data Engineer trong hồ sơ: kiến trúc, dữ liệu, hạ tầng dùng chung, tự động hóa, vận hành và bảo vệ nền tảng.',
        (
            ('Data Architecture', 'Thiết kế kiến trúc, mô hình và hạ tầng xử lý, quản lý, lưu trữ dữ liệu lớn; định hình kho dữ liệu phù hợp công việc AI/ML.'),
            ('Data Engineering', 'Thiết kế, xây dựng, duy trì và tối ưu kho dữ liệu, đường ống dữ liệu chuyển đổi dữ liệu thô thành thông tin có thể sử dụng cho AI/ML.'),
            ('AI Infrastructure & Cost Efficiency', 'Cung ứng, quản lý compute GPU/CPU/TPU, lưu trữ và môi trường dùng chung; đảm bảo tài nguyên sẵn sàng, hiệu năng phù hợp và tối ưu hiệu quả sử dụng chi phí.'),
            ('Platform Automation & Deployment', 'Triển khai Infrastructure-as-Code để tự động hóa thiết lập; hỗ trợ nền tảng, dịch vụ phát triển, triển khai và các đường ống triển khai AI toàn diện.'),
            ('Reliability, Security & Observability', 'Giám sát, ghi nhật ký, báo cáo hiệu năng và khả năng mở rộng; đảm bảo độ tin cậy, quyền truy cập an toàn, mã hóa, bảo mật dữ liệu và tuân thủ quản trị.'),
        ),
    ),
}


def career_target(profile_id):
    title, scope, axes = TARGETS[profile_id]
    return CareerTarget(title=title, scope=scope,
                        axes=[CareerAxisDefinition(name=name, description=description) for name, description in axes])
