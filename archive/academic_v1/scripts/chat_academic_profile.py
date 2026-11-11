#!/usr/bin/env python3
"""Chat tiếng Việt về hồ sơ học thuật và JD hiện tại của SkillBridge."""

from __future__ import annotations

import argparse
import logging
import sys

if __package__:
    from .academic_chat import AcademicChatSession, DEFAULT_SESSION_DIR
    from .academic_review import ReviewError, load_settings
else:
    from academic_chat import AcademicChatSession, DEFAULT_SESSION_DIR
    from academic_review import ReviewError, load_settings


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="data/student_academic_profile.json")
    parser.add_argument("--jd", required=True, help="JD hiện tại dạng .txt UTF-8.")
    parser.add_argument("--review", default="data/jd_academic_review.json", help="Initial Review JSON đã có.")
    persistence = parser.add_mutually_exclusive_group()
    persistence.add_argument("--persist", action="store_true", help="Tạo và lưu một phiên mới.")
    persistence.add_argument("--resume", metavar="SESSION_ID", help="Mở lại UUID phiên đã lưu.")
    parser.add_argument("--session-dir", default=str(DEFAULT_SESSION_DIR))
    parser.add_argument("--max-turns", type=int, default=20)
    parser.add_argument("--max-message-chars", type=int, default=4000)
    parser.add_argument("--context-window", type=int, help="Context model chưa có trong danh sách đã xác nhận.")
    parser.add_argument("--context-budget", type=int, help="Giới hạn tổng input + output budget đã cấu hình.")
    parser.add_argument("--debug", action="store_true", help="Log session/turn/model, không log nội dung.")
    parser.add_argument("--model", help="Override OPENAI_CHAT_MODEL/shared model.")
    parser.add_argument("--reasoning-effort", choices=["none", "low", "medium", "high", "xhigh"])
    parser.add_argument("--max-output-tokens", type=int)
    parser.add_argument("--temperature", type=float, help="Temperature 0–2; bỏ trống khi reasoning được bật.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logger = logging.getLogger("skillbridge.academic_chat")
    handler = None
    previous_level, previous_propagate = logger.level, logger.propagate
    if args.debug:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
    try:
        settings = load_settings(args.context_window, temperature=args.temperature, stage="chat",
                                 model=args.model, reasoning_effort=args.reasoning_effort,
                                 max_output_tokens=args.max_output_tokens)
        with AcademicChatSession.from_files(
            args.profile, args.jd, args.review, context_window=args.context_window,
            settings=settings,
            context_budget=args.context_budget, max_turns=args.max_turns,
            max_message_chars=args.max_message_chars, persist=args.persist,
            resume=args.resume, session_dir=args.session_dir,
        ) as session:
            print("SkillBridge Academic Advisor")
            print(f"\nNhận xét ban đầu: {session.initial_overview}")
            if session.persistent:
                print(f"\nSession ID: {session.session_id}")
            print("\nNhập exit hoặc quit để kết thúc.")
            while True:
                try:
                    message = input("\nBạn: ")
                except (EOFError, KeyboardInterrupt):
                    print("\nĐã kết thúc phiên.")
                    return 0
                if message.strip().casefold() in {"exit", "quit"}:
                    print("Đã kết thúc phiên.")
                    return 0
                try:
                    response = session.send(message)
                except ReviewError as exc:
                    print(f"Lỗi: {exc}", file=sys.stderr)
                    continue
                print(f"\nSkillBridge: {response.reply}")
    except KeyboardInterrupt:
        print("\nĐã kết thúc phiên; không lưu lượt trả lời dở dang.")
        return 0
    except (ReviewError, OSError) as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        return 1
    finally:
        if handler is not None:
            logger.removeHandler(handler)
            handler.close()
            logger.setLevel(previous_level)
            logger.propagate = previous_propagate


if __name__ == "__main__":
    raise SystemExit(main())
