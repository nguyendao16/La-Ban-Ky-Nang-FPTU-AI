from __future__ import annotations

import json

import pytest

from app.services import (
    CourseDataError, CourseService, InconsistentSourceDataError, InvalidMetadataError,
    MissingAssessmentDataError, UnknownCourseError, UnknownCurriculumError,
)

pytestmark = pytest.mark.usefixtures("service_offline")


def test_catalog_isolation_and_explicit_curriculum(service_catalog):
    rows = service_catalog.list_courses()
    assert {r["course_code"] for r in rows} == {"TEST101", "OTHER201"}
    assert all(r["curriculum_code"] == "configured" and r["semester"] == 3 for r in rows)
    assert all(all(r["availability"].values()) for r in rows)
    assert [r["course_code"] for r in service_catalog.list_courses("other")] == ["FOREIGN301"]
    with pytest.raises(UnknownCourseError):
        service_catalog.get_course("FOREIGN301")
    with pytest.raises(UnknownCurriculumError):
        service_catalog.list_courses("BIT_AI_K20C")


@pytest.mark.parametrize("mapping,default", [({}, "x"), ({"x": 3173}, "x"), ({"x": "3173"}, "y"), ({"": "3173"}, "")])
def test_invalid_configuration(mapping, default):
    with pytest.raises(UnknownCurriculumError):
        CourseService(curriculum_mapping=mapping, default_curriculum_code=default)


def test_no_processed_records_for_mapped_id(service_catalog):
    service_catalog._curriculum_mapping["unavailable"] = "42"
    with pytest.raises(UnknownCurriculumError):
        service_catalog.list_courses("unavailable")


def test_raw_metadata_and_definitions_are_copies(service_catalog):
    path = service_catalog.courses_dir / "TEST101"
    raw = json.loads((path / "metadata.json").read_text())
    actual = service_catalog.get_course("TEST101")
    assert actual == raw and actual["tools"] == ""
    actual["tools"] = "Changed by caller"
    assert service_catalog.get_course("TEST101") == raw
    definitions = service_catalog.get_course_assessments("TEST101")
    assert definitions["assessments"] == json.loads((path / "assessments.json").read_text())
    assert definitions["assessments"][0]["weight"] == "25%"
    definitions["assessments"].clear()
    assert len(service_catalog.get_course_assessments("TEST101")["assessments"]) == 2


@pytest.mark.parametrize("method", ["get_course", "get_course_assessments", "get_course_clos"])
@pytest.mark.parametrize("code", ["UNKNOWN", "../TEST101", "test101"])
def test_unknown_courses(service_catalog, method, code):
    with pytest.raises(UnknownCourseError):
        getattr(service_catalog, method)(code)


@pytest.mark.parametrize("content", ["{", '{"subject_code":"WRONG"}', '{"subject_code":"TEST101","subject_code":"TEST101"}'])
def test_invalid_metadata_is_visible_without_removing_membership(service_catalog, content):
    (service_catalog.courses_dir / "TEST101/metadata.json").write_text(content)
    with pytest.raises(InvalidMetadataError):
        service_catalog.get_course("TEST101")
    row = next(r for r in service_catalog.list_courses() if r["course_code"] == "TEST101")
    assert row["availability"]["metadata"] is False
    assert row["diagnostics"][0]["issue"] == "InvalidMetadataError"


@pytest.mark.parametrize("content", [None, "[]"])
def test_missing_assessments(service_catalog, content):
    path = service_catalog.courses_dir / "TEST101/assessments.json"
    if content is None:
        path.unlink()
    else:
        path.write_text(content)
    with pytest.raises(MissingAssessmentDataError):
        service_catalog.get_course_assessments("TEST101")
    row = next(r for r in service_catalog.list_courses() if r["course_code"] == "TEST101")
    assert not row["availability"]["assessments"]


@pytest.mark.parametrize("content", ["{}", "null", '[{"category":"Quiz 1"}]', '[{"category":"Quiz 1","part":"1","weight":"0%","clo":"CLO1"}]'])
def test_inconsistent_assessments(service_catalog, content):
    (service_catalog.courses_dir / "TEST101/assessments.json").write_text(content)
    with pytest.raises(InconsistentSourceDataError):
        service_catalog.get_course_assessments("TEST101")


def test_combo_membership_is_preserved_and_cross_checked(service_catalog):
    path = service_catalog.subjects_dir / "OTHER201.json"
    raw = json.loads(path.read_text())
    raw["record_type"] = "combo_subject"
    raw["combo"] = {"code": "TRACK2", "name": "Alternative", "slot": {"code": "COM*1", "alias": "COM_1", "number": 1}}
    path.write_text(json.dumps(raw))
    slots = [{"combo_code": "TRACK2", "subjects": [{"subject_code": "OTHER201", "slot_code": "COM*1",
              "slot_alias": "COM_1", "slot_number": 1, "semester": 3}]}]
    service_catalog.combo_map_path.write_text(json.dumps(slots))
    row = next(r for r in service_catalog.list_courses() if r["course_code"] == "OTHER201")
    assert row["combo"] == raw["combo"]
    slots[0]["subjects"][0]["slot_number"] = 2
    service_catalog.combo_map_path.write_text(json.dumps(slots))
    with pytest.raises(InconsistentSourceDataError):
        service_catalog.list_courses()


def test_source_id_is_required_and_code_must_match_filename(service_catalog):
    path = service_catalog.subjects_dir / "TEST101.json"
    raw = json.loads(path.read_text())
    raw["source"]["curriculum_url"] = "https://example.test/curriculum"
    path.write_text(json.dumps(raw))
    with pytest.raises(InconsistentSourceDataError):
        service_catalog.list_courses()
    raw["source"]["curriculum_url"] += "?curid=3173"
    raw["subject"]["code"] = "WRONG"
    path.write_text(json.dumps(raw))
    with pytest.raises(InconsistentSourceDataError):
        service_catalog.list_courses()


def test_actual_catalog_includes_unusable_elective_and_twenty_combo_alternatives(actual_course_service):
    rows = actual_course_service.list_courses()
    assert len(rows) == 49 and sum("combo" in row for row in rows) == 20
    elective = next(r for r in rows if r["course_code"] == "AI17_GRA_ELE")
    assert elective["availability"] == {"metadata": False, "assessments": False, "clos": False}
    assert len(elective["diagnostics"]) == 3
    with pytest.raises(InvalidMetadataError):
        actual_course_service.get_course("AI17_GRA_ELE")
    with pytest.raises(MissingAssessmentDataError):
        actual_course_service.get_course_assessments("AI17_GRA_ELE")
    with pytest.raises(CourseDataError):
        actual_course_service.get_course_clos("AI17_GRA_ELE")
