from __future__ import annotations

from uuid import uuid4

from app.services.errors import OperationConflictError, OwnershipLostError, ResourceNotFoundError, SessionNotReadyError, StorageIntegrityError

from .database import digest, json_read, json_text, token_digest, utc_timestamp
from .clo_set_repository import authorized
from .session_repository import SESSION_SELECT, replay_request


class JobRepository:
    def __init__(self, database, sessions):
        self.database = database
        self.sessions = sessions

    def create_recommendations(self, session_id, access_token, key):
        with self.database.transaction(write=True) as connection:
            row = authorized(connection.execute(SESSION_SELECT + ' WHERE s.session_id=?', (session_id,)).fetchone(), access_token)
            snapshot = self.sessions._record(row)['snapshot']
            initial = connection.execute("SELECT status FROM jobs WHERE session_id=? AND job_type='initial_comparison'", (session_id,)).fetchone()
            if initial is None or initial['status'] != 'succeeded' or snapshot['comparison'] is None:
                raise SessionNotReadyError('Comparison must be ready before course suggestions')
            scope = f'recommendations:{session_id}'
            fingerprint = digest({'session_id': session_id, 'comparison': snapshot['fingerprints']['comparison']})
            request = connection.execute('SELECT * FROM requests WHERE owner_hash=? AND scope=? AND key_hash=?',
                (row['owner_hash'], scope, token_digest(key))).fetchone()
            if request:
                return replay_request(request, fingerprint)
            existing = connection.execute("SELECT job_id FROM jobs WHERE session_id=? AND job_type='course_recommendations'", (session_id,)).fetchone()
            job_id = existing['job_id'] if existing else uuid4().hex
            request_id, now = uuid4().hex, utc_timestamp(self.database.clock())
            result = {'job_id': job_id, 'status': 'queued'}
            connection.execute("""INSERT INTO requests(request_id,owner_hash,scope,key_hash,request_fingerprint,
                session_id,status,response_json,created_at,finished_at) VALUES(?,?,?,?,?,?,'succeeded',?,?,?)""",
                (request_id, row['owner_hash'], scope, token_digest(key), fingerprint, session_id, json_text(result), now, now))
            if not existing:
                connection.execute("INSERT INTO jobs(job_id,session_id,request_id,job_type,status,created_at) VALUES(?,?,?,'course_recommendations','queued',?)",
                    (job_id, session_id, request_id, now))
            return result

    def get_recommendations(self, session_id, access_token):
        record = self.sessions.get(session_id, access_token)
        snapshot = record['snapshot']
        with self.database.transaction() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE session_id=? AND job_type='course_recommendations'", (session_id,)).fetchone()
        if row is None:
            return {'session_id': session_id, 'status': 'not_requested', 'job': None, 'result': None, 'gaps': []}
        result, gaps = None, []
        if row['status'] == 'succeeded':
            try:
                from app.engines.recommendations import RecommendationContext, validate_recommendations, public_recommendations
                from app.engines.models import parse_model
                from app.public_view import protect_text
                payload = json_read(row['result_json'])
                if (digest(payload) != row['result_fingerprint']
                        or payload['comparison_fingerprint'] != snapshot['fingerprints']['comparison']):
                    raise ValueError('Recommendation context fingerprint mismatch')
                context = parse_model(RecommendationContext, payload['context']).model_dump()
                generation = validate_recommendations(payload['generation'], context, source=snapshot['clo_set'], check_policy=False).model_dump()
                result = public_recommendations(generation, snapshot['clo_set'])
                gaps = [{**gap, 'description': protect_text(gap['description'], snapshot['clo_set'])} for gap in context['gaps']]
            except (ValueError, TypeError, KeyError) as exc:
                raise StorageIntegrityError('Stored recommendations failed integrity validation') from exc
        elif row['result_json'] is not None or row['result_fingerprint'] is not None:
            raise StorageIntegrityError('Uncommitted recommendation result is present')
        return {'session_id': session_id, 'status': 'ready' if row['status'] == 'succeeded' else row['status'],
                'job': self.sessions.public_job(row), 'result': result, 'gaps': gaps}

    def commit_recommendations(self, lease, raw):
        from app.engines.recommendations import recommendation_context, validate_recommendations
        with self.database.transaction(write=True) as connection:
            row = self.sessions.assert_owned(connection, lease, self.database.clock())
            snapshot = self.sessions._record(row)['snapshot']
            context = recommendation_context(snapshot)
            generated = validate_recommendations(raw, context, source=snapshot['clo_set']).model_dump()
            used = {course['url'] for course in generated['result']['courses']}
            generated['sources'] = [s for s in generated['sources'] if s['url'] in used]
            payload = {'comparison_fingerprint': snapshot['fingerprints']['comparison'],
                       'context': context, 'generation': generated}
            now = self.database.clock()
            changed = connection.execute("""UPDATE jobs SET status='succeeded',finished_at=?,result_json=?,
                result_fingerprint=?,error_code=NULL,error_message=NULL,lease_token=NULL,lease_expires_at=NULL
                WHERE job_id=? AND session_id=? AND job_type='course_recommendations' AND status='processing'
                AND lease_token=? AND lease_generation=? AND lease_expires_at>?""",
                (utc_timestamp(now), json_text(payload), digest(payload), lease.operation_id, lease.session_id,
                 lease.token, lease.generation, now)).rowcount
            if changed != 1:
                raise OwnershipLostError('Recommendation result lost its ownership fence')
            self.sessions._release(connection, lease)

    def claim_next(self):
        self.sessions.recover_expired()
        with self.database.transaction(write=True) as connection:
            row = connection.execute("""SELECT j.job_id,s.* FROM jobs j JOIN sessions s USING(session_id)
                WHERE j.status='queued' AND s.lease_token IS NULL ORDER BY j.created_at,j.job_id LIMIT 1""").fetchone()
            if row is None:
                return None
            now = self.database.clock()
            lease = self.sessions.claim_locked(connection, row, row["job_id"], now)
            changed = connection.execute("""UPDATE jobs SET status='processing',started_at=?,finished_at=NULL,
                attempt_count=attempt_count+1,lease_token=?,lease_generation=?,lease_expires_at=?,last_heartbeat=?
                WHERE job_id=? AND status='queued'""", (utc_timestamp(now), lease.token, lease.generation,
                now + self.database.lease_seconds, utc_timestamp(now), row["job_id"])).rowcount
            if changed != 1:
                raise OwnershipLostError("Comparison claim lost")
            return lease

    def commit_review(self, lease, snapshot):
        with self.database.transaction(write=True) as connection:
            self.sessions.commit_snapshot_locked(connection, lease, snapshot, kind="comparison")
            now = self.database.clock()
            changed = connection.execute("""UPDATE jobs SET status='succeeded',finished_at=?,error_code=NULL,
                error_message=NULL,lease_token=NULL,lease_expires_at=NULL WHERE job_id=? AND status='processing'
                AND lease_token=? AND lease_generation=? AND lease_expires_at>?""",
                (utc_timestamp(now), lease.operation_id, lease.token, lease.generation, now)).rowcount
            if changed != 1:
                raise OwnershipLostError("Comparison result lost its ownership fence")

    def get(self, job_id):
        with self.database.transaction() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                raise ResourceNotFoundError("Job not found")
            return self.sessions.public_job(row)

    def retry(self, job_id, *, acknowledge_possible_duplicate=False):
        """Explicit operator action only; never called by polling/claiming."""
        self.sessions.recover_expired()
        with self.database.transaction(write=True) as connection:
            job = connection.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if job is None:
                raise ResourceNotFoundError("Job not found")
            session = connection.execute("SELECT * FROM sessions WHERE session_id=?", (job["session_id"],)).fetchone()
            if job["status"] not in {"failed", "interrupted"} or session["lease_token"] is not None:
                raise OperationConflictError("Only an unowned failed/interrupted job can be explicitly retried")
            if job["dispatched_at"] is not None and not acknowledge_possible_duplicate:
                raise OperationConflictError("A remote request may have run; acknowledge possible duplicate generation before retry")
            history = json_read(job["recovery_log_json"])
            history.append({"retried_at": utc_timestamp(self.database.clock()), "previous_status": job["status"],
                            "attempt_count": job["attempt_count"], "dispatched_at": job["dispatched_at"],
                            "error_code": job["error_code"], "error_message": job["error_message"],
                            "acknowledged_possible_duplicate": acknowledge_possible_duplicate})
            connection.execute("""UPDATE jobs SET status='queued',started_at=NULL,finished_at=NULL,error_code=NULL,
                error_message=NULL,lease_token=NULL,lease_expires_at=NULL,last_heartbeat=NULL,dispatched_at=NULL,
                recovery_log_json=? WHERE job_id=?""", (json_text(history), job_id))
            return {"job_id": job_id, "status": "queued"}

    def worker_heartbeat(self, worker_id, *, state="running"):
        with self.database.transaction(write=True) as connection:
            now, stamp = self.database.clock(), utc_timestamp(self.database.clock())
            connection.execute("""INSERT INTO workers VALUES(?,?,?,?,?) ON CONFLICT(worker_id)
                DO UPDATE SET last_heartbeat=excluded.last_heartbeat,last_seen_epoch=excluded.last_seen_epoch,state=excluded.state""",
                (worker_id, stamp, stamp, now, state))
