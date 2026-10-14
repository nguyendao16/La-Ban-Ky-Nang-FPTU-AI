from __future__ import annotations

import argparse
import json
import random
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

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


def is_combo_placeholder(subject: dict[str, Any]) -> bool:
    code = str(subject.get("subject_code", ""))
    name = str(subject.get("subject_name", "")).lower()
    return bool(re.search(r"\*\d+$", code)) and "combo" in name


def combo_slot_number(subject_code: str) -> int | None:
    match = re.search(r"\*(\d+)$", subject_code)
    return int(match.group(1)) if match else None


def combo_family(subject_code: str) -> str:
    return re.sub(r"\*\d+$", "", subject_code)


def normalized_slot_alias(subject_code: str) -> str:
    # AI17_COM*1 -> AI17_COM_1, convenient as a filename / external label.
    return re.sub(r"\*(\d+)$", r"_\1", subject_code)


def build_combo_groups(subjects: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for subject in subjects:
        if not is_combo_placeholder(subject):
            continue
        key = (combo_family(subject["subject_code"]), subject["semester"])
        enriched = dict(subject)
        enriched["combo_slot_number"] = combo_slot_number(subject["subject_code"])
        enriched["combo_slot_alias"] = normalized_slot_alias(subject["subject_code"])
        groups[key].append(enriched)

    for slots in groups.values():
        slots.sort(key=lambda item: item["combo_slot_number"] or 10**9)
    return dict(groups)


def parse_pre_syllabus(html: str, pre_url: str) -> list[dict[str, Any]]:
    """Parse a normal (non-combo) Pre_Syllabus page."""
    soup = BeautifulSoup(html, "html.parser")
    syllabus_table = None
    for table in soup.find_all("table"):
        headers = [clean_text(th) for th in table.find_all("th")]
        if "Syllabus Name" in headers and "IsActive" in headers and "IsApproved" in headers:
            # Combo pages also have Syllabus Name, but include a Note column and a Comboes heading.
            if "Note" not in headers:
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


def parse_combo_page(
    html: str,
    pre_url: str,
    semester_slots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Parse one FLM combo page.

    Important FLM behavior:
    - A combo page can contain several combo choices (h3 headings).
    - Each combo choice contains one row per curriculum combo slot in that semester.
      Example: semester 5 has AI17_COM*1 and AI17_COM*2, so each combo table has 2 rows.
    - The row order is mapped to the ordered curriculum slots for that semester.
    """
    soup = BeautifulSoup(html, "html.parser")
    combo_heading = soup.find(lambda tag: tag.name == "h2" and clean_text(tag).lower() == "comboes")
    if combo_heading is None:
        return []

    container = combo_heading.parent
    options: list[dict[str, Any]] = []

    for h3 in container.find_all("h3", recursive=False):
        title = clean_text(h3)
        if not title:
            continue

        if ":" in title:
            code, name = title.split(":", 1)
            option_code = code.strip()
            option_name = name.strip()
        else:
            option_code = title
            option_name = ""

        note_tag = h3.find_next_sibling("h4")
        table = h3.find_next_sibling("table")
        if table is None:
            continue

        option_note = clean_text(note_tag) if note_tag else ""
        members: list[dict[str, Any]] = []

        rows = table.select("tbody tr")
        data_row_index = 0
        for tr in rows:
            cells = tr.find_all("td", recursive=False)
            if len(cells) < 6:
                continue

            detail_link = cells[1].find("a", href=True)
            if not detail_link or "SyllabusDetails?" not in detail_link["href"]:
                continue

            slot = semester_slots[data_row_index] if data_row_index < len(semester_slots) else None
            data_row_index += 1
            active_box = cells[3].find("input", {"type": "checkbox"})
            approved_box = cells[4].find("input", {"type": "checkbox"})
            details_url = urljoin(BASE_URL, detail_link["href"])
            syl_id = parse_qs(urlparse(details_url).query).get("sylID", [None])[0]

            member = {
                "combo_code": option_code,
                "combo_name": option_name,
                "combo_title": title,
                "combo_note": option_note,
                "combo_page_url": pre_url,
                "slot_code": slot["subject_code"] if slot else None,
                "slot_alias": slot["combo_slot_alias"] if slot else None,
                "slot_number": slot["combo_slot_number"] if slot else None,
                "slot_subject_name": slot["subject_name"] if slot else None,
                "semester": slot["semester"] if slot else None,
                "credits": slot["credits"] if slot else None,
                "actual_subject_code": clean_text(cells[0]),
                "syllabus_name": clean_text(detail_link),
                "row_note": clean_text(cells[2], preserve_lines=True),
                "is_active": bool(active_box and active_box.has_attr("checked")),
                "is_approved": bool(approved_box and approved_box.has_attr("checked")),
                "decision_no": clean_text(cells[5]),
                "syllabus_id": syl_id,
                "syllabus_url": details_url,
                "details": None,
                "error": None,
            }
            members.append(member)

        options.append(
            {
                "combo_code": option_code,
                "combo_name": option_name,
                "combo_title": title,
                "combo_note": option_note,
                "source_url": pre_url,
                "members": members,
            }
        )

    return options


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


def attach_combo_context(details: dict[str, Any], member: dict[str, Any]) -> dict[str, Any]:
    """Put explicit curriculum/combo ownership next to the syllabus details."""
    result = dict(details)
    result["combo_context"] = {
        "is_combo_subject": True,
        "combo_code": member["combo_code"],
        "combo_name": member["combo_name"],
        "combo_title": member["combo_title"],
        "combo_note": member["combo_note"],
        "curriculum_slot_code": member["slot_code"],
        "curriculum_slot_alias": member["slot_alias"],
        "curriculum_slot_number": member["slot_number"],
        "curriculum_slot_name": member["slot_subject_name"],
        "semester": member["semester"],
        "actual_subject_code": member["actual_subject_code"],
        "actual_subject_name": member["syllabus_name"],
    }
    return result


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
    """Authenticated HTTP GET using the browser context cookie jar, with browser fallback."""
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
    combos_dir = output_dir / "combos"
    subjects_dir.mkdir(exist_ok=True)
    combos_dir.mkdir(exist_ok=True)

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
        all_subjects = parse_curriculum(curriculum_html, curriculum_url)
        combo_groups = build_combo_groups(all_subjects)

        subjects_to_process = all_subjects if limit is None else all_subjects[:limit]
        selected_codes = {subject["subject_code"] for subject in subjects_to_process}

        # If --limit lands on one combo slot, process the whole semester combo group so row->slot
        # mapping remains correct.
        combo_group_keys_to_process: set[tuple[str, str]] = set()
        for subject in subjects_to_process:
            if is_combo_placeholder(subject):
                combo_group_keys_to_process.add(
                    (combo_family(subject["subject_code"]), subject["semester"])
                )

        normal_subjects = [s for s in subjects_to_process if not is_combo_placeholder(s)]
        print(f"Tim thay {len(all_subjects)} subject(s) trong curriculum.")
        print(
            f"Se crawl {len(normal_subjects)} mon thuong va "
            f"{len(combo_group_keys_to_process)} combo semester group(s)."
        )

        index_by_code: dict[str, dict[str, Any]] = {}
        details_cache: dict[str, dict[str, Any]] = {}
        combo_tracks: dict[str, dict[str, Any]] = {}

        def get_details(syllabus_url: str) -> dict[str, Any]:
            if syllabus_url in details_cache:
                return details_cache[syllabus_url]
            detail_html = fetch_html(api, page, syllabus_url)
            details = parse_syllabus_details(detail_html, syllabus_url)
            details_cache[syllabus_url] = details
            return details

        # -----------------------------
        # Normal subjects
        # -----------------------------
        for i, subject in enumerate(normal_subjects, start=1):
            code = subject["subject_code"]
            print(f"[normal {i}/{len(normal_subjects)}] {code}")

            record: dict[str, Any] = {
                "record_type": "normal_subject",
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
                    record["details"] = get_details(selected["syllabus_url"])

            except Exception as exc:
                record["error"] = f"{type(exc).__name__}: {exc}"

            out_path = subjects_dir / f"{safe_filename(code)}.json"
            out_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

            index_by_code[code] = {
                "subject_code": code,
                "subject_name": subject["subject_name"],
                "semester": subject["semester"],
                "record_type": "normal_subject",
                "syllabus_id": (record["selected_syllabus"] or {}).get("syllabus_id"),
                "status": "ok" if record["details"] else "error",
                "error": record["error"],
                "file": str(out_path),
            }
            time.sleep(random.uniform(min_delay, max_delay))

        # -----------------------------
        # Combo placeholders
        # -----------------------------
        for group_index, key in enumerate(sorted(combo_group_keys_to_process), start=1):
            family, semester = key
            slots = combo_groups[key]
            source_slot = slots[0]
            print(
                f"[combo {group_index}/{len(combo_group_keys_to_process)}] "
                f"{family} semester {semester}: "
                + ", ".join(slot["subject_code"] for slot in slots)
            )

            slot_records: dict[str, dict[str, Any]] = {}
            for slot in slots:
                slot_records[slot["subject_code"]] = {
                    "record_type": "combo_slot",
                    "curriculum": slot,
                    "combo_family": family,
                    "combo_slot_number": slot["combo_slot_number"],
                    "combo_slot_alias": slot["combo_slot_alias"],
                    "combo_options": [],
                    "error": None,
                }

            try:
                pre_html = fetch_html(api, page, source_slot["pre_syllabus_url"])
                options = parse_combo_page(pre_html, source_slot["pre_syllabus_url"], slots)
                if not options:
                    raise RuntimeError("Khong parse duoc Comboes tren Pre_Syllabus page")

                for option in options:
                    track = combo_tracks.setdefault(
                        option["combo_code"],
                        {
                            "combo_code": option["combo_code"],
                            "combo_name": option["combo_name"],
                            "combo_title": option["combo_title"],
                            "combo_note": option["combo_note"],
                            "combo_family": family,
                            "subjects": [],
                        },
                    )

                    for member in option["members"]:
                        if not member["slot_code"]:
                            member["error"] = "No curriculum combo slot matched this row"
                            continue

                        try:
                            time.sleep(random.uniform(min_delay, max_delay))
                            raw_details = get_details(member["syllabus_url"])
                            member["details"] = attach_combo_context(raw_details, member)
                        except Exception as exc:
                            member["error"] = f"{type(exc).__name__}: {exc}"

                        slot_record = slot_records[member["slot_code"]]
                        slot_record["combo_options"].append(
                            {
                                "combo_code": member["combo_code"],
                                "combo_name": member["combo_name"],
                                "combo_title": member["combo_title"],
                                "combo_note": member["combo_note"],
                                "subject": {
                                    "actual_subject_code": member["actual_subject_code"],
                                    "syllabus_name": member["syllabus_name"],
                                    "row_note": member["row_note"],
                                    "is_active": member["is_active"],
                                    "is_approved": member["is_approved"],
                                    "decision_no": member["decision_no"],
                                    "syllabus_id": member["syllabus_id"],
                                    "syllabus_url": member["syllabus_url"],
                                    "details": member["details"],
                                    "error": member["error"],
                                },
                            }
                        )

                        track["subjects"].append(
                            {
                                "slot_code": member["slot_code"],
                                "slot_alias": member["slot_alias"],
                                "slot_number": member["slot_number"],
                                "slot_subject_name": member["slot_subject_name"],
                                "semester": member["semester"],
                                "credits": member["credits"],
                                "actual_subject_code": member["actual_subject_code"],
                                "syllabus_name": member["syllabus_name"],
                                "syllabus_id": member["syllabus_id"],
                                "syllabus_url": member["syllabus_url"],
                                "is_active": member["is_active"],
                                "is_approved": member["is_approved"],
                                "decision_no": member["decision_no"],
                                "details": member["details"],
                                "error": member["error"],
                            }
                        )

            except Exception as exc:
                group_error = f"{type(exc).__name__}: {exc}"
                for slot_record in slot_records.values():
                    slot_record["error"] = group_error

            # Write one file per curriculum placeholder slot, e.g. AI17_COM_1.json.
            for slot in slots:
                code = slot["subject_code"]
                record = slot_records[code]
                out_path = subjects_dir / f"{safe_filename(code)}.json"
                out_path.write_text(
                    json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
                )

                option_count = len(record["combo_options"])
                detail_count = sum(
                    1
                    for option in record["combo_options"]
                    if option.get("subject", {}).get("details") is not None
                )
                if detail_count == option_count and option_count > 0:
                    status = "ok"
                elif detail_count > 0:
                    status = "partial"
                else:
                    status = "error"

                index_by_code[code] = {
                    "subject_code": code,
                    "subject_alias": slot["combo_slot_alias"],
                    "subject_name": slot["subject_name"],
                    "semester": slot["semester"],
                    "record_type": "combo_slot",
                    "combo_family": family,
                    "combo_slot_number": slot["combo_slot_number"],
                    "combo_option_count": option_count,
                    "status": status,
                    "error": record["error"],
                    "file": str(out_path),
                }

            time.sleep(random.uniform(min_delay, max_delay))

        # Sort subjects inside each combo track by slot number, then write one complete file per combo choice.
        combo_index: list[dict[str, Any]] = []
        for code, track in sorted(combo_tracks.items()):
            track["subjects"].sort(key=lambda item: item["slot_number"] or 10**9)
            track_path = combos_dir / f"{safe_filename(code)}.json"
            track_path.write_text(json.dumps(track, ensure_ascii=False, indent=2), encoding="utf-8")
            combo_index.append(
                {
                    "combo_code": code,
                    "combo_name": track["combo_name"],
                    "subject_count": len(track["subjects"]),
                    "slots": [item["slot_code"] for item in track["subjects"]],
                    "actual_subject_codes": [item["actual_subject_code"] for item in track["subjects"]],
                    "file": str(track_path),
                }
            )

        (combos_dir / "index.json").write_text(
            json.dumps(combo_index, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # Keep the curriculum order in the main index.
        order = {subject["subject_code"]: i for i, subject in enumerate(all_subjects)}
        index = sorted(index_by_code.values(), key=lambda item: order.get(item["subject_code"], 10**9))
        (output_dir / "index.json").write_text(
            json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        print(f"\nDone. Output: {output_dir.resolve()}")
        print(f"Combo tracks: {(combos_dir / 'index.json').resolve()}")
        context.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Crawl FLM Curriculum -> Syllabuses/Comboes -> SyllabusDetails"
    )
    parser.add_argument("curriculum_url", help="URL CurriculumDetails, vd: ...?curid=3173")
    parser.add_argument("--profile-dir", default=DEFAULT_PROFILE_DIR)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--min-delay", type=float, default=0.7)
    parser.add_argument("--max-delay", type=float, default=1.4)
    parser.add_argument("--limit", type=int, default=None, help="Test truoc N curriculum rows")
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
