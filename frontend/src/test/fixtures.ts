import type {
  JDComparison,
  Catalog,
  Course,
  Selection,
  Session,
  CareerProfile,
  CareerComparison,
  CareerRadarData,
  Comparison,
  CourseDetail,
} from "../types";
export const token = "test-capability-never-rendered";
export const course = (code: string): Course => ({
  course_code: code,
  name: { vi: `Môn ${code}` },
  semester: 1,
  credits: 3,
  curriculum_code: "configured",
});
export const catalog: Catalog = {
  curriculum_code: "configured",
  courses: [
    "TEST101",
    "OTHER201",
    "MID201",
    "LATE301",
    "FOUR401",
    "COMBOA",
    "COMBOB",
    "COMMON5",
    "EXTRA",
    "S7",
    "S8",
    "S9",
  ].map(course),
  semester_map: {
    common: [
      { semester: 1, course_codes: ["TEST101", "OTHER201"] },
      { semester: 2, course_codes: ["MID201"] },
      { semester: 3, course_codes: ["LATE301"] },
      { semester: 4, course_codes: ["FOUR401"] },
    ],
    combos: ["Applied Data Science", "AI application"].map((name, i) => ({
      name,
      semesters: [
        { semester: 5, course_codes: [i ? "COMBOB" : "COMBOA", "COMMON5"] },
        { semester: 6, course_codes: ["EXTRA"] },
        { semester: 7, course_codes: ["S7"] },
        { semester: 8, course_codes: ["S8"] },
        { semester: 9, course_codes: ["S9"] },
      ],
    })),
  },
};
export const detail = (code: string): CourseDetail => course(code);
export const selection: Selection = {
  selection_id: "selection-1",
  curriculum_code: "configured",
  status: "ready",
  summary: { course_count: 1 },
  selected_courses: ["TEST101"],
  created_at: "2026-10-17",
};
export const comparison: Comparison = {
  comparison_type: "course_jd_comparison",
  overview: "Tổng quan so sánh từ backend.",
  requirement_reviews: [
    {
      jd_requirement: "SQL",
      coverage: "not_evidenced",
      comment: "Chưa có bằng chứng đối chiếu cho yêu cầu này.",
      evidence: [],
    },
  ],
  conclusion: "Đối chiếu nội dung môn học và JD.",
};
export const session = (status: Session["status"]): Session => ({
  session_id: "session-1",
  selection_id: "selection-1",
  status,
  target: { type: "jd", job_description: "SQL" },
  comparison: status === "ready" ? comparison : null,
  comparison_job: {
    job_id: "job-1",
    status: status === "ready" ? "succeeded" : status,
  },
  revision: status === "ready" ? 1 : 0,
  turn_count: 0,
  created_at: "2026-10-17",
  updated_at: "2026-10-17",
});
export const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });

export const careerProfiles: CareerProfile[] = [
  ["data-scientist", "Data Scientist"],
  ["data-analyst", "Data Analyst"],
  ["ai-ml-engineer", "Machine Learning Engineer"],
  ["computer-vision-engineer", "Computer Vision Engineer"],
  ["nlp-llm-engineer", "NLP / LLM Engineer"],
  ["mlops-engineer", "MLOps Engineer"],
  ["ai-researcher", "Algorithm Research Engineer"],
  ["ai-data-platform-engineer", "AI & Data Platform Engineer"],
].map(([profile_id, title]) => ({
  profile_id,
  title,
  standard: "CWA 18398:2026",
  role_codes: ["1.1"],
  content: `Mô tả ${title}`,
  fingerprint: "fixture-hash",
}));
export const careerRadar: CareerRadarData = {
  overall_score: 3.7,
  overall_comment: "Nhận định tổng thể của LLM về nội dung các môn đã chọn.",
  axes: [
    ["Dữ liệu và thống kê", 4],
    ["Phân tích nghiệp vụ", 3.5],
    ["Mô hình dự báo", 2],
    ["Triển khai mô hình", 1.5],
    ["Truyền đạt kết quả", 3],
  ].map(([name, score]) => ({
    name: String(name),
    score: Number(score),
    description: `Phạm vi của trục ${name} đối với nhóm nghề mục tiêu.`,
    comment: `Nội dung học phần có liên hệ với ${name}; đây không phải đánh giá năng lực cá nhân.`,
    evidence: [{ course_code: "TEST101" }],
  })),
};
export const careerComparison: CareerComparison = {
  radar: careerRadar,
  comparison_type: "career_comparison",
  overview: "Góc nhìn nghề nghiệp từ backend.",
  related_content: [
    {
      title: "Nền tảng dữ liệu",
      comment: "Các môn liên quan đến thao tác dữ liệu.",
      evidence: [{ course_code: "TEST101" }],
    },
  ],
  gaps: [
    {
      title: "Triển khai thực tế",
      comment: "Nội dung học tập chưa đề cập vận hành hệ thống.",
      evidence: [],
    },
  ],
  conclusion: "Có thể tìm hiểu thêm phạm vi công việc này.",
};

export const longCareerComparison: CareerComparison = {
  radar: {
    ...careerRadar,
    axes: careerRadar.axes.map((axis) => ({
      ...axis,
      evidence: [{ course_code: "COMMON101" }],
    })),
  },
  comparison_type: "career_comparison",
  overview:
    "Bối cảnh đầy đủ của phép đối chiếu, bao gồm phạm vi dữ liệu và điều kiện phân tích.",
  conclusion:
    "Nội dung các môn đã chọn có những liên hệ nền tảng với nhóm nghề mục tiêu. " +
    "Các liên hệ này phản ánh nội dung học tập, không chứng minh sinh viên đã có kinh nghiệm thực tế. ".repeat(
      12,
    ) +
    "Những nội dung chưa được thể hiện cần được đọc trong phạm vi dữ liệu đã cung cấp.",
  related_content: Array.from({ length: 12 }, (_, i) => ({
    title: `Nhóm nội dung ${i + 1}: nền tảng xử lý dữ liệu và tư duy phân tích`,
    comment:
      `Phân tích đầy đủ nhóm ${i + 1}. ` +
      "Môn học cung cấp bối cảnh để tìm hiểu chủ đề; bằng chứng này không xác nhận năng lực thực hành. ".repeat(
        3,
      ),
    evidence: [
      { course_code: `COURSE${String(i + 1).padStart(2, "0")}` },
      { course_code: "COMMON101" },
    ],
  })),
  gaps: Array.from({ length: 7 }, (_, i) => ({
    title: `Khoảng trống ${i + 1}: các hoạt động trong môi trường nghề nghiệp`,
    comment: `Giới hạn phân tích ${i + 1}: dữ liệu của các môn đã chọn chưa thể hiện rõ phạm vi nội dung này. Không thể từ đó kết luận chương trình không giảng dạy hoặc sinh viên không có khả năng thực hiện.`,
    evidence: [{ course_code: "GAP999" }],
  })),
};

export const longJDComparison: JDComparison = {
  comparison_type: "course_jd_comparison",
  overview:
    "Bối cảnh đối chiếu JD: giữ nguyên các điều kiện bắt buộc, ưu tiên và AND/OR.",
  conclusion:
    "Nội dung các môn đã chọn có liên hệ với yêu cầu của JD. " +
    "Các liên hệ phản ánh nội dung học tập, không xác nhận năng lực cá nhân hoặc kinh nghiệm làm việc. ".repeat(
      8,
    ),
  requirement_reviews: Array.from({ length: 12 }, (_, i) => ({
    jd_requirement: `Yêu cầu ${i + 1}: Python và SQL hoặc công cụ xử lý dữ liệu tương đương`,
    coverage: (["covered", "related", "not_evidenced"] as const)[i % 3],
    comment: `Phân tích đầy đủ yêu cầu ${i + 1}. Phân biệt điều kiện bắt buộc và ưu tiên; nội dung liên quan không xác nhận kinh nghiệm thực tế.`,
    evidence:
      i % 3 === 2
        ? []
        : [{ course_code: `COURSE${String(i + 1).padStart(2, "0")}` }],
  })),
  radar: {
    ...careerRadar,
    overall_comment:
      "Nhận định tổng thể của LLM theo JD đã nhập, không phải trung bình năm trục.",
    axes: careerRadar.axes.map((axis, i) => ({
      ...axis,
      name: [
        "Lập trình Python",
        "Truy vấn SQL",
        "Phân tích nghiệp vụ",
        "Vận hành dữ liệu",
        "Trình bày kết quả",
      ][i],
      description: `Phạm vi trục ${i + 1} gắn với JD hiện tại.`,
      comment: `Giải thích điểm trục ${i + 1} theo nội dung các môn đã chọn.`,
      evidence: [{ course_code: "COURSE01" }],
    })),
  },
};
