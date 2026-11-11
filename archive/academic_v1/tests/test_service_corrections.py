import copy
import json

import pytest

from app.services import ProfileService, ScoreValidationError, UnknownCourseError
from scripts.academic_chat import AcademicChatSession, ChatError

pytestmark = pytest.mark.usefixtures("service_offline")


def test_requested_curriculum_is_consistent_for_all_getters_and_profile(service_catalog):
    for method in ["get_course", "get_course_clos", "get_course_assessments"]:
        assert getattr(service_catalog, method)("FOREIGN301", "other")
        with pytest.raises(UnknownCourseError): getattr(service_catalog, method)("FOREIGN301")
    profile = ProfileService(service_catalog).build_profile(["FOREIGN301"], {"FOREIGN301": {"Quiz 1": 7, "Final exam": 7}}, curriculum_code="other")
    assert profile["courses"][0]["course_code"] == "FOREIGN301"
    with pytest.raises(UnknownCourseError):
        ProfileService(service_catalog).build_profile(["FOREIGN301", "TEST101"], {}, curriculum_code="other")


def grades_for(catalog, codes):
    return {c: {a["category"]: 8 for a in catalog.get_course_assessments(c)["assessments"]} for c in codes}


def test_actual_combo_source_establishes_four_choice_slots(actual_course_service):
    constraints = actual_course_service.get_selection_constraints()
    assert len(constraints["exclusive_slots"]) == 4 and not constraints["ambiguous_slots"]
    assert all(len(s["course_codes"]) == 5 for s in constraints["exclusive_slots"])
    codes = ["BDI302c", "GAI201m"]
    with pytest.raises(ScoreValidationError) as error:
        ProfileService(actual_course_service).build_profile(codes, grades_for(actual_course_service, codes))
    issue = error.value.issues[0]
    assert issue == {"issue": "duplicate_combo_slot_selection", "curriculum_code": "fixture-source-3173",
                     "slot_identifier": "AI17_COM*1", "conflicting_course_codes": codes}


@pytest.mark.parametrize("codes", [["BDI302c", "MOI201m"], ["MAE101", "MAD101"]])
def test_distinct_slots_and_ordinary_same_semester_courses_are_valid(actual_course_service, codes):
    profile = ProfileService(actual_course_service).build_profile(codes, grades_for(actual_course_service, codes))
    assert [c["course_code"] for c in profile["courses"]] == codes


def test_missing_authoritative_slot_records_remain_ambiguous(actual_course_service, tmp_path):
    actual_course_service.combo_slots_dir = tmp_path
    constraints = actual_course_service.get_selection_constraints()
    assert not constraints["exclusive_slots"] and len(constraints["ambiguous_slots"]) == 4
    codes = ["BDI302c", "GAI201m"]
    assert ProfileService(actual_course_service).build_profile(codes, grades_for(actual_course_service, codes))


def test_snapshot_roundtrip_is_detached_and_has_no_files(service_profile, tmp_path):
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    with AcademicChatSession.from_data(service_profile, " SQL\n") as original:
        snapshot = original.export_snapshot()
    with AcademicChatSession.from_snapshot(snapshot) as restored:
        assert restored.session_id == snapshot["session_id"] and not restored.persistent
        assert restored.export_snapshot() == snapshot
        snapshot["profile"]["courses"][0]["clos"].clear()
        exported = restored.export_snapshot()
        assert exported["profile"]["courses"][0]["clos"]
        exported["fingerprints"].clear()
        assert restored.export_snapshot()["fingerprints"]
    assert {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize("change", ["id", "fingerprint", "profile", "jd", "history", "key", "version"])
def test_snapshot_import_reuses_existing_integrity_validation(service_profile, change):
    with AcademicChatSession.from_data(service_profile, "SQL") as session:
        snapshot = session.export_snapshot()
    if change == "id": snapshot["session_id"] = "not-a-uuid"
    elif change == "fingerprint": snapshot["fingerprints"]["profile"] = "0" * 64
    elif change == "profile": snapshot["profile"]["courses"][0]["clos"][0]["score"] = 1
    elif change == "jd": snapshot["job_description"] += "\n"
    elif change == "history": snapshot["messages"] = [{"role": "user", "content": "unfinished"}]
    elif change == "key": snapshot["api_key"] = "must not persist"
    elif change == "version": snapshot["version"] = 1
    with pytest.raises(ChatError): AcademicChatSession.from_snapshot(snapshot)
