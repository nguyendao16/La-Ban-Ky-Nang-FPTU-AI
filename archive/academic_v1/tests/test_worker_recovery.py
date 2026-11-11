import pytest

from app.jobs.heartbeat import OperationHeartbeat
from app.jobs.review_worker import ReviewWorker
from app.services.errors import OperationConflictError, OwnershipLostError


def test_expired_review_is_interrupted_not_requeued_and_stale_commit_is_rejected(api_backend, queued_session):
    lease = api_backend.backend.jobs.claim_next()
    original = api_backend.backend.sessions.load_owned(lease)
    updated, _ = api_backend.advisor.review_snapshot(original)
    api_backend.clock.advance(31)
    assert api_backend.backend.sessions.recover_expired() == 1
    assert api_backend.backend.jobs.get(lease.operation_id)["status"] == "interrupted"
    with pytest.raises(OwnershipLostError): api_backend.backend.jobs.commit_review(lease, updated)
    assert ReviewWorker(api_backend.backend.jobs, api_backend.advisor).run_once() is None
    stored = api_backend.backend.sessions.get(lease.session_id, queued_session["access_token"])
    assert stored["snapshot"]["review"] is None and stored["revision"] == 0
    assert api_backend.review_client.responses.parse.call_count == 1


def test_heartbeat_renews_only_current_owner_and_fences_old_recovery_generation(api_backend, queued_session):
    lease = api_backend.backend.jobs.claim_next()
    heartbeat = OperationHeartbeat(api_backend.backend.sessions, lease, 5)
    api_backend.clock.advance(20)
    assert heartbeat.pulse()
    api_backend.clock.advance(20)
    assert api_backend.backend.sessions.recover_expired() == 0  # Original lease expired, renewal did not.
    api_backend.backend.sessions.mark_dispatched(lease)
    api_backend.clock.advance(31)
    api_backend.backend.sessions.recover_expired()
    with pytest.raises(OperationConflictError): api_backend.backend.jobs.retry(lease.operation_id)
    api_backend.backend.jobs.retry(lease.operation_id, acknowledge_possible_duplicate=True)
    newer = api_backend.backend.jobs.claim_next()
    assert newer.generation > lease.generation
    assert not heartbeat.pulse()
    with pytest.raises(OwnershipLostError): heartbeat.check()
    with pytest.raises(OwnershipLostError): api_backend.backend.sessions.renew(lease)
    assert api_backend.backend.sessions.load_owned(newer)["review"] is None


def test_explicit_pre_dispatch_retry_and_audit_do_not_execute_inference(api_backend, queued_session):
    lease = api_backend.backend.jobs.claim_next()
    api_backend.backend.sessions.finish_failure(lease, status="failed", code="configuration", message="Not dispatched")
    assert api_backend.backend.jobs.retry(lease.operation_id)["status"] == "queued"
    api_backend.review_client.responses.parse.assert_not_called()
    with api_backend.database.transaction() as connection:
        row = connection.execute("SELECT recovery_log_json FROM jobs").fetchone()[0]
        assert "Not dispatched" in row and '"acknowledged_possible_duplicate":false' in row


def test_revision_mismatch_rejects_commit_even_with_matching_token(api_backend, queued_session):
    lease = api_backend.backend.jobs.claim_next()
    snapshot, _ = api_backend.advisor.review_snapshot(api_backend.backend.sessions.load_owned(lease))
    with api_backend.database.transaction(write=True) as connection:
        connection.execute("UPDATE sessions SET revision=revision+1 WHERE session_id=?", (lease.session_id,))
    with pytest.raises(OwnershipLostError): api_backend.backend.jobs.commit_review(lease, snapshot)
