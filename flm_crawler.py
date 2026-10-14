from __future__ import annotations

import argparse
import json
import random
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse, parse_qs

from bs4 import BeautifulSoup, Tag
from playwright.sync_api import APIRequestContext, Page, sync_playwright

BASE_URL = "https://flm.fpt.edu.vn"
DEFAULT_PROFILE_DIR = ".flm_profile"
DEFAULT_OUTPUT_DIR = "flm_output"


def clean_text(node: Tag | None, preserve_lines: bool = False) -> str:
    if node is None:
        return ""
    sep = "\n" if preserve_lines else " "
    text = node.get_text(sep, strip=True)
    if preserve_lines:
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
        return "\n".join(line for line in lines if line)
    return re.sub(r"\s+", " ", text).strip()


def table_to_dicts(table: Tag | None) -> list[dict[str, str]]:
    if table is None:
        return []

    headers = [clean_text(th) for th in table.select("thead th")]
    if not headers:
        first_row = table.find("tr")
        if first_row:
            headers = [clean_text(cell) for cell in first_row.find_all(["th", "td"], recursive=False)]

    rows: list[dict[str, str]] = []
    body_rows = table.select("tbody tr") or table.find_all("tr")[1:]
    for tr in body_rows:
        cells = tr.find_all("td", recursive=False)
        if not cells:
            continue
        values = [clean_text(td, preserve_lines=True) for td in cells]
        if headers:
            row = {headers[i]: values[i] if i < len(values) else "" for i in range(len(headers))}
        else:
            row = {f"col_{i+1}": value for i, value in enumerate(values)}
        rows.append(row)
    return rows


def parse_curriculum(html: str, curriculum_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("#gvSubs")
    if table is None:
        raise RuntimeError("Khong tim thay bang #gvSubs trong Curriculum Details.")

    subjects: list[dict[str, Any]] = []
    for tr in table.select("tbody tr"):
        cells = tr.find_all("td", recursive=False)
        if len(cells) < 5:
            continue

        link = cells[1].find("a", href=True)
        if not link or "Syllabuses?" not in link["href"]:
            continue

        pre_url = urljoin(BASE_URL, link["href"])
        subjects.append(
            {
                "subject_code": clean_text(cells[0]),
                "subject_name": clean_text(link),
                "semester": clean_text(cells[2]),
                "credits": clean_text(cells[3]),
                "prerequisite": clean_text(cells[4]),
                "pre_syllabus_url": pre_url,
                "curriculum_url": curriculum_url,
            }
        )
    return subjects


def parse_pre_syllabus(html: str, pre_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    syllabus_table = None
    for table in soup.find_all("table"):
        headers = [clean_text(th) for th in table.find_all("th")]
        if "Syllabus Name" in headers and "IsActive" in headers and "IsApproved" in headers:
            syllabus_table = table
            break

    if syllabus_table is None:
        return []

    versions: list[dict[str, Any]] = []
    for tr in syllabus_table.select("tbody tr"):
        cells = tr.find_all("td", recursive=False)
        if len(cells) < 5:
            continue

        detail_link = cells[1].find("a", href=True)
        if not detail_link or "SyllabusDetails?" not in detail_link["href"]:
            continue

        active_box = cells[2].find("input", {"type": "checkbox"})
        approved_box = cells[3].find("input", {"type": "checkbox"})
        details_url = urljoin(BASE_URL, detail_link["href"])
        syl_id = parse_qs(urlparse(details_url).query).get("sylID", [None])[0]

        versions.append(
            {
                "subject_code": clean_text(cells[0]),
                "syllabus_name": clean_text(detail_link),
                "is_active": bool(active_box and active_box.has_attr("checked")),
                "is_approved": bool(approved_box and approved_box.has_attr("checked")),
                "decision_no": clean_text(cells[4]),
                "syllabus_id": syl_id,
                "syllabus_url": details_url,
                "pre_syllabus_url": pre_url,
            }
        )
    return versions


def choose_current_version(versions: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not versions:
        return None

    priority_groups = [
        [v for v in versions if v["is_active"] and v["is_approved"]],
        [v for v in versions if v["is_approved"]],
        [v for v in versions if v["is_active"]],
        versions,
    ]
    for group in priority_groups:
        if group:
            return group[0]
    return None


def parse_metadata_table(table: Tag | None) -> dict[str, str]:
    data: dict[str, str] = {}
    if table is None:
        return data
    for tr in table.select("tr"):
        cells = tr.find_all("td", recursive=False)
        if len(cells) < 2:
            continue
        key = clean_text(cells[0]).rstrip(":").strip()
        value = clean_text(cells[1], preserve_lines=True)
        if key:
            data[key] = value
    return data


def parse_syllabus_details(html: str, syllabus_url: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    metadata = parse_metadata_table(soup.select_one("#table-detail"))
    if not metadata:
        raise RuntimeError(f"Khong parse duoc Syllabus Details: {syllabus_url}")

    return {
        "source_url": syllabus_url,
        "metadata": metadata,
        "materials": table_to_dicts(soup.select_one("#gvMaterial")),
        "clos": table_to_dicts(soup.select_one("#gvLO")),
        "schedule": table_to_dicts(soup.select_one("#gvSchedule")),
        "assessments": table_to_dicts(soup.select_one("#gvAssessment")),
    }


def looks_like_login(html: str, response_url: str) -> bool:
    url_lower = response_url.lower()
    html_lower = html.lower()
    if "login" in url_lower and "flm.fpt.edu.vn" in url_lower:
        return True
    login_markers = [
        'type="password"',
        "signin",
        "sign in",
        "/home/login",
    ]
    return any(marker in html_lower for marker in login_markers) and "#gvsubs" not in html_lower


def fetch_html(api: APIRequestContext, page: Page, url: str) -> str:
    """Fast path: authenticated HTTP GET using the same cookie jar as the browser.
    Fallback: normal browser navigation if the server returns a login page.
    """
    response = api.get(url, timeout=60_000, fail_on_status_code=False)
    html = response.text()

    if response.status >= 400 or looks_like_login(html, response.url):
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        html = page.content()

    return html


def safe_filename(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")
    return value or "unknown"


def ensure_logged_in(page: Page, curriculum_url: str) -> None:
    page.goto(curriculum_url, wait_until="domcontentloaded", timeout=60_000)
    if page.locator("#gvSubs").count() > 0:
        return

    print("\nFLM chua o trang Curriculum Details co #gvSubs.")
    print("Hay dang nhap FPT/FEID trong cua so Chromium vua mo.")
    print("Sau khi dang nhap xong, mo lai Curriculum Details neu can.")
    input("Nhan Enter trong terminal de tiep tuc crawl... ")

    page.goto(curriculum_url, wait_until="domcontentloaded", timeout=60_000)
    if page.locator("#gvSubs").count() == 0:
        raise RuntimeError(
            "Van khong tim thay #gvSubs. Kiem tra dang nhap, URL curriculum, hoac quyen truy cap."
        )


def crawl(
    curriculum_url: str,
    profile_dir: Path,
    output_dir: Path,
    min_delay: float,
    max_delay: float,
    limit: int | None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    subjects_dir = output_dir / "subjects"
    subjects_dir.mkdir(exist_ok=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            headless=False,
            viewport={"width": 1280, "height": 900},
        )
        page = context.pages[0] if context.pages else context.new_page()
        ensure_logged_in(page, curriculum_url)

        api = context.request
        curriculum_html = fetch_html(api, page, curriculum_url)
        subjects = parse_curriculum(curriculum_html, curriculum_url)

        if limit is not None:
            subjects = subjects[:limit]

        print(f"Tim thay {len(subjects)} subject(s) trong curriculum.")

        index: list[dict[str, Any]] = []
        for i, subject in enumerate(subjects, start=1):
            code = subject["subject_code"]
            print(f"[{i}/{len(subjects)}] {code}")

            record: dict[str, Any] = {
                "curriculum": subject,
                "syllabus_versions": [],
                "selected_syllabus": None,
                "details": None,
                "error": None,
            }

            try:
                pre_html = fetch_html(api, page, subject["pre_syllabus_url"])
                versions = parse_pre_syllabus(pre_html, subject["pre_syllabus_url"])
                record["syllabus_versions"] = versions

                selected = choose_current_version(versions)
                record["selected_syllabus"] = selected

                if selected is None:
                    record["error"] = "No syllabus version found"
                else:
                    time.sleep(random.uniform(min_delay, max_delay))
                    detail_html = fetch_html(api, page, selected["syllabus_url"])
                    record["details"] = parse_syllabus_details(detail_html, selected["syllabus_url"])

            except Exception as exc:  # continue with remaining subjects
                record["error"] = f"{type(exc).__name__}: {exc}"

            out_path = subjects_dir / f"{safe_filename(code)}.json"
            out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

            index.append(
                {
                    "subject_code": code,
                    "subject_name": subject["subject_name"],
                    "semester": subject["semester"],
                    "syllabus_id": (record["selected_syllabus"] or {}).get("syllabus_id"),
                    "status": "ok" if record["details"] else "error",
                    "error": record["error"],
                    "file": str(out_path),
                }
            )

            time.sleep(random.uniform(min_delay, max_delay))

        (output_dir / "index.json").write_text(
            json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nDone. Output: {output_dir.resolve()}")
        context.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Crawl FLM Curriculum -> Syllabuses -> SyllabusDetails")
    parser.add_argument("curriculum_url", help="URL CurriculumDetails, vd: ...?curid=3172")
    parser.add_argument("--profile-dir", default=DEFAULT_PROFILE_DIR)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--min-delay", type=float, default=0.7)
    parser.add_argument("--max-delay", type=float, default=1.4)
    parser.add_argument("--limit", type=int, default=None, help="Test truoc N mon")
    args = parser.parse_args()

    if args.min_delay < 0 or args.max_delay < args.min_delay:
        raise SystemExit("Delay khong hop le")

    crawl(
        curriculum_url=args.curriculum_url,
        profile_dir=Path(args.profile_dir),
        output_dir=Path(args.output_dir),
        min_delay=args.min_delay,
        max_delay=args.max_delay,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
