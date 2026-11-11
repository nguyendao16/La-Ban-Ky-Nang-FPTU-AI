import copy
import json
from pathlib import Path

import pytest

from app.services import CLOSetService, CourseDataError, CLOSetValidationError, UnknownCourseError

pytestmark = pytest.mark.usefixtures("service_offline")


def test_enriched_source_order_is_exact_and_metadata_is_not_a_dependency(service_catalog):
    (service_catalog.courses_dir / "TEST101/metadata.json").unlink()
    (service_catalog.courses_dir / "TEST101/assessments.json").unlink()
    service = CLOSetService(service_catalog)
    result = service.build_clo_set(["OTHER201", "TEST101"])
    assert [c["course_code"] for c in result["courses"]] == ["OTHER201", "TEST101"]
    assert result["courses"][1]["clos"] == json.loads((service_catalog.courses_dir / "TEST101/clos.json").read_text())
    assert set(result) == {"courses"} and set(result["courses"][0]) == {"course_code", "clos"}
    result["courses"][0]["clos"].clear()
    assert service.build_clo_set(["OTHER201"])["courses"][0]["clos"]


@pytest.mark.parametrize("selection", [None, [], "TEST101", [True], [""], ["TEST101", "TEST101"]])
def test_invalid_selection_is_rejected(service_catalog, selection):
    with pytest.raises(CLOSetValidationError): CLOSetService(service_catalog).build_clo_set(selection)


def test_curriculum_isolation_and_unknown_course(service_catalog):
    service = CLOSetService(service_catalog)
    assert service.build_clo_set(["FOREIGN301"], curriculum_code="other")
    with pytest.raises(UnknownCourseError): service.build_clo_set(["FOREIGN301"])
    with pytest.raises(UnknownCourseError): service.build_clo_set(["UNKNOWN"])


@pytest.mark.parametrize("clos", [[], [{"clo": "CLO1", "description": ""}], [{"clo": "CLO1", "description": "SQL", "score": 8}],
    [{"clo": "CLO1", "description": "SQL"}, {"clo": "CLO1", "description": "SQL 2"}], {"CLO1": "SQL"}])
def test_invalid_canonical_clos_disable_availability(service_catalog, clos):
    (service_catalog.courses_dir / "TEST101/clos.json").write_text(json.dumps(clos))
    row = next(r for r in service_catalog.list_courses() if r["course_code"] == "TEST101")
    assert row["availability"]["clos"] is False
    with pytest.raises(CourseDataError): CLOSetService(service_catalog).build_clo_set(["TEST101"])


def test_raw_metadata_is_display_only_and_empty_tools_preserved(service_catalog):
    raw = service_catalog.get_course("TEST101")
    assert raw["tools"] == "" and raw["source_note"] == "Keep this extra raw field"
    row = next(r for r in service_catalog.list_courses() if r["course_code"] == "TEST101")
    assert set(row["availability"]) == {"clos", "metadata"}
    assert not hasattr(service_catalog, "get_course_assessments")


def test_actual_catalog_has_enriched_source_and_four_exclusive_slots(actual_course_service):
    service = CLOSetService(actual_course_service)
    constraints = actual_course_service.get_selection_constraints()
    assert len(constraints["exclusive_slots"]) == 4
    assert all(len(s["course_codes"]) == 5 for s in constraints["exclusive_slots"])
    with pytest.raises(CLOSetValidationError) as error:
        service.build_clo_set(["BDI302c", "GAI201m"])
    assert error.value.issues[0]["issue"] == "duplicate_combo_slot_selection"
    assert service.build_clo_set(["BDI302c", "MOI201m"])
    assert service.build_clo_set(["MAE101", "MAD101"])
    rows = actual_course_service.list_courses()
    assert len(rows) == 49 and sum(r["availability"]["clos"] for r in rows) == 48
    with pytest.raises(CourseDataError): service.build_clo_set(["AI17_GRA_ELE"])
    source = service.build_clo_set(["ADY201m"])
    assert source["courses"][0]["clos"] == json.loads(Path('data/courses/ADY201m/clos.json').read_text())
    assert len(source["courses"][0]["clos"]) == 7


def test_absent_combo_descriptors_remain_ambiguous(actual_course_service, tmp_path):
    actual_course_service.combo_slots_dir = tmp_path
    constraints = actual_course_service.get_selection_constraints()
    assert not constraints["exclusive_slots"] and len(constraints["ambiguous_slots"]) == 4
    assert CLOSetService(actual_course_service).build_clo_set(["BDI302c", "GAI201m"])
