"""Disposable API + separate fake Comparison worker for the real frontend.

Run: python -m examples.offline_demo
Only the launcher creates the marked temporary directory. Internal child roles
cannot operate on an arbitrary student database. No OpenAI key is needed.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from app.config import BackendSettings
from app.jobs.review_worker import ReviewWorker
from app.main import create_app
from app.services import AdvisorService
from app.storage.database import Database
from app.storage.job_repository import JobRepository
from app.storage.session_repository import SessionRepository
from app.llm import LLMSettings
from examples.services_integration import mock_career_radar, mock_jd_radar, mock_recommendation_response

DEMO_DIRECTORY = "SKILLBRIDGE_OFFLINE_DEMO_DIR"


class OfflineResponses:
    """Mock Responses interface; evidence comes from the actual input snapshot."""

    def __init__(self, stage, *, review_delay=2):
        self.stage, self.review_delay = stage, review_delay
        self.input_tokens = SimpleNamespace(count=self.count)

    def count(self, **kwargs):
        return SimpleNamespace(input_tokens=100)

    def parse(self, **kwargs):
        if self.stage == 'recommendations':
            time.sleep(self.review_delay)
            return mock_recommendation_response(json.loads(kwargs['input'][0]['content']))
        if self.stage == "review":
            source = json.loads(kwargs["input"][0]["content"])["clo_set"]
            evidence = [] if not source['courses'] else [{"course_code": source['courses'][0]['course_code'], "clo": source['courses'][0]['clos'][0]['clo']}]
            time.sleep(self.review_delay)
            raw = {"radar": mock_jd_radar(evidence), "comparison_type": "clo_jd_comparison",
                "overview": "DEMO OFFLINE: minh họa đối chiếu môn học và yêu cầu công việc. Nội dung được giả lập.",
                "requirement_reviews": [{"jd_requirement": "Yêu cầu trong JD của phiên demo",
                    "coverage": "related" if evidence else "not_evidenced",
                    "comment": "DEMO: nội dung môn học có liên quan đến chủ đề trong JD." if evidence else "Chưa có bằng chứng đối chiếu cho yêu cầu này.",
                    "evidence": evidence}],
                "conclusion": "DEMO OFFLINE: chỉ đối chiếu nội dung, không đánh giá năng lực cá nhân."}
            target = json.loads(kwargs["input"][1]["content"])
            if "career_profile" in target:
                profile = target["career_profile"]
                title = profile.get('target', {}).get('title', profile['title'])
                raw = {"comparison_type": "career_comparison",
                    "overview": f"DEMO OFFLINE: góc nhìn nội dung học tập với nhóm nghề {title}. Phân tích được giả lập.",
                    "related_content": [{"title": "Nền tảng học tập liên quan", "comment": "DEMO: nội dung môn học gợi mở một số liên hệ nền tảng với công việc mục tiêu.", "evidence": evidence}] if evidence else [],
                    "gaps": [{"title": "Phạm vi công việc cần tìm hiểu", "comment": "DEMO: nội dung môn học chưa thể hiện đầy đủ các hoạt động thực tế của nhóm nghề.", "evidence": []}],
                    "conclusion": "DEMO OFFLINE: đối chiếu nội dung học tập, không kết luận về năng lực cá nhân.",
                    "radar": mock_career_radar(target["career_profile"], evidence)}
        else:
            evidence = json.loads(kwargs["input"][1]["content"])["permitted_evidence"][:1]
            raw = {"reply": "DEMO OFFLINE: kết quả mô tả quan hệ giữa nội dung môn học và yêu cầu công việc. Câu trả lời được giả lập.", "evidence": evidence}
            for message in kwargs['input']:
                if message['role'] != 'user':
                    continue
                try:
                    saved = json.loads(message['content']).get('saved_recommendations')
                except (ValueError, AttributeError):
                    continue
                if saved and saved['courses']:
                    course = saved['courses'][0]
                    raw['reply'] = f"DEMO OFFLINE: {course['title']} ({course['url']}) được gợi ý cho khoảng trống đã lưu. Đây là thông tin giả lập, không xác nhận nội dung một khóa Coursera thật."
                    break
        return SimpleNamespace(status="completed", output=[], output_parsed=raw)


def demo_advisor(*, review_delay=2):
    return AdvisorService(
        review_settings=LLMSettings(api_key="offline-demo-placeholder", stage="review"),
        chat_settings=LLMSettings(api_key="offline-demo-placeholder", stage="chat"),
        review_client=SimpleNamespace(responses=OfflineResponses("review", review_delay=review_delay)),
        chat_client=SimpleNamespace(responses=OfflineResponses("chat")),
        recommendation_client=SimpleNamespace(responses=OfflineResponses('recommendations', review_delay=review_delay)))


def demo_settings(directory):
    return BackendSettings(database_path=Path(directory) / "offline.sqlite3",
        curriculum_mapping={"source-3173": "3173"}, default_curriculum="source-3173",
        cors_origins=(os.environ.get('SKILLBRIDGE_DEMO_FRONTEND_ORIGIN', 'http://localhost:5173'),))


def marked_directory():
    raw = os.environ.get(DEMO_DIRECTORY)
    if not raw:
        raise ValueError("Use the offline demo launcher")
    directory = Path(raw).resolve()
    if not directory.name.startswith("skillbridge-ui-demo-") or not (directory / ".offline-demo").is_file():
        raise ValueError("Offline mode requires a launcher-created disposable directory")
    return directory


def run_fake_worker(directory):
    settings = demo_settings(directory)
    database = Database(settings.database_path, lease_seconds=settings.lease_seconds)
    database.initialize()
    advisor = demo_advisor()
    sessions = SessionRepository(database, advisor.validate_snapshot)
    worker = ReviewWorker(JobRepository(database, sessions), advisor, heartbeat_interval=settings.heartbeat_interval)
    stop = threading.Event()

    def interrupt(signum, frame):
        if not stop.is_set():
            stop.set()
            raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupt)
    try:
        while not stop.is_set():
            worker.run_once()
            stop.wait(.25)
    except KeyboardInterrupt:
        stop.set()
    finally:
        worker.close()
        advisor.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--role", choices=["api", "worker"], help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.role:
        directory = marked_directory()
        if args.role == "worker":
            run_fake_worker(directory)
        else:
            import uvicorn
            uvicorn.run(create_app(demo_settings(directory), advisor_service=demo_advisor()),
                        host="127.0.0.1", port=args.port, log_level="warning", access_log=False)
        return 0
    children = []
    shutting_down = False
    def stop_launcher(signum, frame):
        nonlocal shutting_down
        if not shutting_down:
            shutting_down = True
            raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop_launcher)
    with tempfile.TemporaryDirectory(prefix="skillbridge-ui-demo-") as directory:
        Path(directory, ".offline-demo").touch(mode=0o600)
        environment = {**os.environ, DEMO_DIRECTORY: directory}
        try:
            for role in ["api", "worker"]:
                children.append(subprocess.Popen([sys.executable, "-m", "examples.offline_demo",
                    "--role", role, "--port", str(args.port)], env=environment))
            print(f"DEMO OFFLINE — API http://127.0.0.1:{args.port}; SQLite tạm; worker giả lập riêng; không gọi OpenAI.", flush=True)
            while all(child.poll() is None for child in children):
                time.sleep(.5)
            return 1
        except KeyboardInterrupt:
            shutting_down = True
            return 0
        finally:
            for child in children:
                if child.poll() is None:
                    child.terminate()
            for child in children:
                try:
                    child.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
