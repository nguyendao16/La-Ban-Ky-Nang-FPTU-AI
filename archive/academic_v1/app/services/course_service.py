"""Read curriculum membership and canonical course data without inference."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from scripts.clo_scoring import parse_weight
from scripts.course_metadata import read_course_metadata

from .errors import (
    CourseDataError, InconsistentSourceDataError, InvalidMetadataError,
    MissingAssessmentDataError, UnknownCourseError, UnknownCurriculumError,
)

ROOT = Path(__file__).resolve().parents[2]


def _read_json(path: Path) -> Any:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate source field: {key}")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError(f"Invalid JSON constant: {value}")

    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique,
                          parse_constant=invalid_constant)
    except (OSError, UnicodeError, ValueError) as exc:
        raise InconsistentSourceDataError(f"Cannot read valid source JSON: {path}") from exc


class CourseService:
    """Curriculum aliases must be supplied by the caller, never inferred.

    Assessment identities are the source category within its course. Weights
    remain source percentage strings/numbers, rather than invented fractions.
    """

    def __init__(
        self, *, curriculum_mapping: Mapping[str, str], default_curriculum_code: str,
        courses_dir: Path | str = ROOT / "data/courses",
        subjects_dir: Path | str = ROOT / "data/stage1/subjects",
        combo_map_path: Path | str = ROOT / "data/stage1/combo_slot_map.json",
        combo_slots_dir: Path | str = ROOT / "data/flm_output/subjects",
    ):
        if not isinstance(curriculum_mapping, Mapping) or not curriculum_mapping:
            raise UnknownCurriculumError("Provide an explicit curriculum code/source-ID mapping")
        if any(not isinstance(k, str) or not k.strip() or not isinstance(v, str) or not v.strip()
               for k, v in curriculum_mapping.items()):
            raise UnknownCurriculumError("Curriculum codes and source IDs must be nonblank strings")
        self._curriculum_mapping = dict(curriculum_mapping)
        self.default_curriculum_code = default_curriculum_code
        self.courses_dir = Path(courses_dir)
        self.subjects_dir = Path(subjects_dir)
        self.combo_map_path = Path(combo_map_path)
        self.combo_slots_dir = Path(combo_slots_dir)
        self._source_id(default_curriculum_code)

    def _source_id(self, code: str) -> str:
        if not isinstance(code, str) or code not in self._curriculum_mapping:
            raise UnknownCurriculumError(f"Unconfigured curriculum: {code!r}")
        return self._curriculum_mapping[code]

    def _index(self, curriculum_code: str) -> dict[str, dict[str, Any]]:
        source_id = self._source_id(curriculum_code)
        if not self.subjects_dir.is_dir():
            raise CourseDataError(f"Missing processed subject directory: {self.subjects_dir}")
        result = {}
        for path in sorted(self.subjects_dir.glob("*.json")):
            raw = _read_json(path)
            try:
                ids = parse_qs(urlparse(raw["source"]["curriculum_url"]).query).get("curid", [])
                if len(ids) != 1:
                    raise ValueError("Missing or ambiguous source curriculum ID")
                if ids[0] != source_id:
                    continue
                subject = raw["subject"]
                code = subject["code"]
                if (not isinstance(code, str) or code != path.stem or code in result
                        or not isinstance(subject["name"], dict)
                        or "semester" not in subject
                        or raw["record_type"] not in {"normal_subject", "combo_subject"}):
                    raise ValueError("Invalid or inconsistent processed subject")
                result[code] = raw
            except (KeyError, TypeError, ValueError, AttributeError) as exc:
                raise InconsistentSourceDataError(f"Invalid curriculum source: {path}") from exc
        if not result:
            raise UnknownCurriculumError(f"No processed records for curriculum {curriculum_code!r} ({source_id})")
        combo_subjects = [raw for raw in result.values() if raw["record_type"] == "combo_subject"]
        if combo_subjects:
            combos = _read_json(self.combo_map_path)
            if not isinstance(combos, list):
                raise InconsistentSourceDataError("COMBO slot map must be an array")
            for raw in combo_subjects:
                try:
                    combo = raw["combo"]
                    matches = [s for c in combos if c["combo_code"] == combo["code"]
                               for s in c["subjects"] if s["subject_code"] == raw["subject"]["code"]]
                    if len(matches) != 1:
                        raise ValueError("COMBO membership missing or duplicated")
                    match = matches[0]
                    if (match["slot_code"] != combo["slot"]["code"]
                            or match["slot_alias"] != combo["slot"]["alias"]
                            or match["slot_number"] != combo["slot"]["number"]
                            or match["semester"] != raw["subject"]["semester"]):
                        raise ValueError("COMBO slot mismatch")
                except (KeyError, TypeError, ValueError) as exc:
                    raise InconsistentSourceDataError("Processed COMBO membership is inconsistent") from exc
        return result

    def _require_course(self, course_code: str, curriculum_code: str | None = None) -> dict[str, Any]:
        records = self._index(self.default_curriculum_code if curriculum_code is None else curriculum_code)
        if not isinstance(course_code, str) or course_code not in records:
            raise UnknownCourseError(f"Course is not in the configured curriculum: {course_code!r}")
        return records[course_code]

    def _metadata(self, code: str) -> dict[str, Any]:
        try:
            return copy.deepcopy(read_course_metadata(self.courses_dir, code))
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            raise InvalidMetadataError(f"Invalid or missing metadata for {code}") from exc

    def _assessments(self, code: str) -> list[dict[str, Any]]:
        path = self.courses_dir / code / "assessments.json"
        if not path.is_file():
            raise MissingAssessmentDataError(f"Missing assessment data for {code}")
        raw = _read_json(path)
        if isinstance(raw, list) and not raw:
            raise MissingAssessmentDataError(f"No assessment definitions for {code}")
        if not isinstance(raw, list):
            raise InconsistentSourceDataError(f"Assessments must be an array for {code}")
        categories = set()
        for item in raw:
            try:
                category = item["category"]
                if (not isinstance(category, str) or not category.strip() or category != category.strip()
                        or category in categories or not isinstance(item["part"], str)
                        or "clo" not in item or isinstance(item["weight"], bool)):
                    raise ValueError("Invalid or duplicate assessment category")
                parse_weight(item["weight"])
                categories.add(category)
            except (KeyError, TypeError, ValueError) as exc:
                raise InconsistentSourceDataError(f"Invalid assessment definition for {code}") from exc
        return raw

    def _clos(self, code: str) -> list[dict[str, Any]]:
        raw = _read_json(self.courses_dir / code / "clos.json")
        if not isinstance(raw, list) or not raw:
            raise CourseDataError(f"No usable canonical CLO data for {code}")
        seen = set()
        for item in raw:
            if not isinstance(item, dict):
                raise InconsistentSourceDataError(f"Invalid CLO data for {code}")
            identifier = item.get("clo") or item.get("clo_name")
            description = item.get("description") or item.get("clo_details")
            if (not isinstance(identifier, str) or not identifier.strip() or identifier in seen
                    or not isinstance(description, str) or not description.strip()):
                raise InconsistentSourceDataError(f"Invalid or duplicate CLO data for {code}")
            seen.add(identifier)
        return raw

    def list_courses(self, curriculum_code: str | None = None) -> list[dict[str, Any]]:
        code = self.default_curriculum_code if curriculum_code is None else curriculum_code
        result = []
        for course_code, raw in self._index(code).items():
            availability, diagnostics = {}, []
            for field, reader in [("metadata", self._metadata), ("assessments", self._assessments), ("clos", self._clos)]:
                try:
                    reader(course_code)
                    availability[field] = True
                except CourseDataError as exc:
                    availability[field] = False
                    diagnostics.append({"field": field, "issue": type(exc).__name__, "message": str(exc)})
            row = {"course_code": course_code, **copy.deepcopy(raw["subject"]),
                   "record_type": raw["record_type"], "curriculum_code": code,
                   "curriculum_source_id": self._source_id(code),
                   "availability": availability, "diagnostics": diagnostics}
            if "combo" in raw:
                row["combo"] = copy.deepcopy(raw["combo"])
            result.append(row)
        return result

    def get_course(self, course_code: str, curriculum_code: str | None = None) -> dict[str, Any]:
        self._require_course(course_code, curriculum_code)
        return self._metadata(course_code)

    def get_course_assessments(self, course_code: str, curriculum_code: str | None = None) -> dict[str, Any]:
        self._require_course(course_code, curriculum_code)
        return {"course_code": course_code, "assessments": copy.deepcopy(self._assessments(course_code))}

    def get_course_clos(self, course_code: str, curriculum_code: str | None = None) -> list[dict[str, Any]]:
        """Canonical definitions for profile validation; this does not score CLOs."""
        self._require_course(course_code, curriculum_code)
        return copy.deepcopy(self._clos(course_code))

    def get_selection_constraints(self, curriculum_code: str | None = None) -> dict[str, Any]:
        """Only source combo_slot/alternatives establish one curricular choice.

        Shared semesters or track names are insufficient. Missing source slots
        remain ambiguous, rather than becoming invented enrollment rules.
        """
        code = self.default_curriculum_code if curriculum_code is None else curriculum_code
        records = self._index(code)
        groups = {}
        for path in sorted(self.combo_slots_dir.glob("*.json")):
            raw = _read_json(path)
            if not isinstance(raw, dict) or raw.get("record_type") != "combo_slot":
                continue
            try:
                curriculum = raw["curriculum"]
                ids = parse_qs(urlparse(curriculum["curriculum_url"]).query).get("curid", [])
                if ids != [self._source_id(code)]:
                    continue
                slot, family, options = curriculum["subject_code"], raw["combo_family"], raw["combo_options"]
                if not isinstance(slot, str) or not isinstance(family, str) or not isinstance(options, list):
                    raise ValueError("Invalid slot")
                alternatives = []
                for option in options:
                    course = option["subject"]["actual_subject_code"]
                    if course not in records:
                        continue
                    context = records[course].get("combo", {})
                    if (context.get("code") != option["combo_code"]
                            or context.get("family") != family or context["slot"]["code"] != slot):
                        raise ValueError("Slot options disagree with processed membership")
                    alternatives.append(course)
                if (family, slot) in groups or len(set(alternatives)) != len(alternatives):
                    raise ValueError("Duplicate slot/alternative")
                groups[(family, slot)] = {"curriculum_code": code, "family": family,
                                          "slot_identifier": slot, "course_codes": alternatives}
            except (KeyError, TypeError, ValueError) as exc:
                raise InconsistentSourceDataError(f"Invalid source COMBO slot: {path}") from exc
        unresolved = sorted({r["combo"]["slot"]["code"] for r in records.values()
                             if "combo" in r and (r["combo"].get("family"), r["combo"]["slot"]["code"]) not in groups})
        return {"exclusive_slots": list(groups.values()), "ambiguous_slots": unresolved}
