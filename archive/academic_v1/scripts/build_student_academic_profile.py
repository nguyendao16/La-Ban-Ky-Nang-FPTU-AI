#!/usr/bin/env python3
"""Build a deterministic student academic profile from course assessment grades."""

from __future__ import annotations

import argparse
from pathlib import Path

if __package__:
    from .clo_scoring import build_student_academic_profile
else:
    from clo_scoring import build_student_academic_profile


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--academic-report",
        default="academic_report.json",
        help="Path to the student's academic report JSON.",
    )
    parser.add_argument(
        "--courses-dir",
        default="data/courses",
        help="Directory containing canonical course folders.",
    )
    parser.add_argument(
        "--output",
        default="data/student_academic_profile.json",
        help="Path for the generated academic profile JSON.",
    )
    parser.add_argument(
        "--report-output",
        default="data/clo_scoring_report.json",
        help="Path for the generated scoring validation report JSON.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    profile, report = build_student_academic_profile(
        academic_report_path=Path(args.academic_report),
        courses_dir=Path(args.courses_dir),
        output_path=Path(args.output),
        report_output_path=Path(args.report_output),
    )

    print(f"Wrote academic profile: {args.output}")
    print(f"Wrote scoring report: {args.report_output}")
    print(f"Processed courses: {report['processed_courses']}/{report['academic_report_courses']}")
    print(f"Evaluated CLOs: {report['clos_with_scores']}/{report['total_clos_evaluated']}")
    print(f"Courses in profile: {len(profile['courses'])}")
    print(f"Metadata coverage: {report['courses_with_metadata']}/{report['processed_courses']}")
    for error in report["metadata_validation_errors"]:
        print(f"Metadata warning [{error['course_code']}]: {error['issue']} ({error['path']})")
    if report["courses_could_not_be_processed"]:
        print(f"Courses not processed: {len(report['courses_could_not_be_processed'])}")
    if report["missing_or_unmatched_assessment_grades"]:
        print(f"Missing or unmatched assessment grades: {len(report['missing_or_unmatched_assessment_grades'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
