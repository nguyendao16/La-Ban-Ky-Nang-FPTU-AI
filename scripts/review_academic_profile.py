#!/usr/bin/env python3
"""Tạo review kiến thức học thuật tiếng Việt từ profile và JD bằng OpenAI."""

from __future__ import annotations

import argparse
import sys

from academic_review import ReviewError, load_settings, review_files


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="data/student_academic_profile.json", help="Hồ sơ học thuật JSON UTF-8.")
    parser.add_argument("--jd", required=True, help="JD dạng file .txt UTF-8.")
    parser.add_argument("--output", default="data/jd_academic_review.json", help="File JSON review đầu ra.")
    parser.add_argument("--context-window", type=int, help="Giới hạn context đã xác nhận của model (tokens).")
    parser.add_argument("--model", help="Override OPENAI_REVIEW_MODEL/shared model.")
    parser.add_argument("--reasoning-effort", choices=["none", "low", "medium", "high", "xhigh"])
    parser.add_argument("--max-output-tokens", type=int)
    parser.add_argument("--temperature", type=float, help="Temperature 0–2; bỏ trống khi reasoning được bật.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        settings = load_settings(args.context_window, temperature=args.temperature, stage="review",
                                 model=args.model, reasoning_effort=args.reasoning_effort,
                                 max_output_tokens=args.max_output_tokens)
        review = review_files(args.profile, args.jd, args.output, context_window=args.context_window, settings=settings)
    except (ReviewError, OSError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1
    print(f"Đã lưu review học thuật: {args.output}")
    print(f"Số yêu cầu JD được nhận xét: {len(review.requirement_reviews)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
