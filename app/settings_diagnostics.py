"""Inspect resolved stage configuration offline, without requiring credentials."""

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv
from app.llm import ComparisonError, load_settings


def resolved_settings():
    result = {}
    for stage in ("review", "chat"):
        # A placeholder permits inspection without an actual API key. It never
        # leaves this process: no SDK client or network operation is constructed.
        settings = load_settings(stage=stage, api_key="diagnostic-only")
        result[stage] = {"model": settings.model, "reasoning_effort": settings.reasoning_effort,
                         "max_output_tokens": settings.max_output_tokens,
                         "request_timeout": settings.timeout}
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, help="Optional local file; process environment takes precedence.")
    args = parser.parse_args(argv)
    if args.env_file is not None:
        if not args.env_file.is_file():
            parser.error("Configuration file does not exist")
        load_dotenv(args.env_file, override=False)
    try:
        print(json.dumps(resolved_settings(), ensure_ascii=False, indent=2))
    except ComparisonError:
        print(json.dumps({"error": "Invalid model configuration; check stage settings"}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
