"""
Credits and analysis tests: starting an analysis, credit reservation and
refund, idempotency, ownership, running the worker in mock mode, reports,
and progress.

The Celery task is faked (see conftest.queued_tasks), so "run_worker" below
calls the real task function directly, in-process.
"""

import uuid

from sqlalchemy import select

from app.models.analysis import Analysis
from app.models.credit_transaction import CreditTransaction
from app.workers import analysis_worker


def start(client, account, recording_id, key=None):
    headers = dict(account.headers)
    if key:
        headers["Idempotency-Key"] = key
    return client.post("/api/v1/analysis/start", headers=headers, json={"recording_id": recording_id})


def remaining(client, account) -> int:
    return client.get("/api/v1/usage", headers=account.headers).json()["remaining"]


def run_worker(analysis_id: str) -> None:
    """Runs the real Celery task function in-process (mock analysis mode)."""
    analysis_worker.run_analysis.run(analysis_id)


def setup_take(client, account, upload_song, upload_recording):
    song = upload_song(account)
    rec = upload_recording(account, song["id"])
    return song, rec


# ---------------- starting ----------------
def test_start_requires_auth(client):
    r = client.post("/api/v1/analysis/start", json={"recording_id": str(uuid.uuid4())})
    assert r.status_code == 401


def test_start_reserves_one_credit_and_queues(client, user_a, upload_song, upload_recording, queued_tasks):
    _, rec = setup_take(client, user_a, upload_song, upload_recording)
    r = start(client, user_a, rec["id"])
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "QUEUED"
    assert body["is_simulated"] is True            # mock mode is always labelled
    assert body["credits_remaining"] == 9
    assert remaining(client, user_a) == 9
    assert len(queued_tasks.calls) == 1
    assert queued_tasks.calls[0]["args"] == [body["analysis_id"]]


def test_idempotency_key_prevents_double_charge(client, user_a, upload_song, upload_recording, queued_tasks):
    _, rec = setup_take(client, user_a, upload_song, upload_recording)
    first = start(client, user_a, rec["id"], key="same-key-12345").json()
    second = start(client, user_a, rec["id"], key="same-key-12345").json()
    assert second["analysis_id"] == first["analysis_id"]
    assert second["duplicate"] is True
    assert remaining(client, user_a) == 9
    assert len(queued_tasks.calls) == 1


def test_double_tap_without_key_is_one_analysis(client, user_a, upload_song, upload_recording):
    _, rec = setup_take(client, user_a, upload_song, upload_recording)
    a = start(client, user_a, rec["id"]).json()
    b = start(client, user_a, rec["id"]).json()
    assert a["analysis_id"] == b["analysis_id"]
    assert remaining(client, user_a) == 9


def test_no_credits_blocks_start(client, user_a, upload_song, upload_recording, db):
    _, rec = setup_take(client, user_a, upload_song, upload_recording)
    # use up all credits with different keys
    for i in range(10):
        assert start(client, user_a, rec["id"], key=f"key-number-{i:04d}").status_code == 202
    r = start(client, user_a, rec["id"], key="key-number-9999")
    assert r.status_code == 403
    err = r.json()["error"]
    assert err["code"] == "USAGE_LIMIT_REACHED"
    assert err["upgrade_required"] is True
    assert remaining(client, user_a) == 0
    # the refused request left no analysis and no charge behind
    assert len(db.scalars(select(Analysis)).all()) == 10


def test_queue_failure_refunds_credit(client, user_a, upload_song, upload_recording, queued_tasks):
    _, rec = setup_take(client, user_a, upload_song, upload_recording)
    queued_tasks.fail = True
    r = start(client, user_a, rec["id"])
    assert r.status_code == 503
    assert remaining(client, user_a) == 10


def test_cannot_start_on_someone_elses_recording(client, user_a, user_b, upload_song, upload_recording):
    _, rec = setup_take(client, user_a, upload_song, upload_recording)
    assert start(client, user_b, rec["id"]).status_code == 404
    assert remaining(client, user_b) == 10


def test_unknown_recording_is_404(client, user_a):
    assert start(client, user_a, str(uuid.uuid4())).status_code == 404


# ---------------- status, worker, report ----------------
def test_status_then_complete_then_report(client, user_a, upload_song, upload_recording, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)   # skip the mock's demo delays
    _, rec = setup_take(client, user_a, upload_song, upload_recording)
    aid = start(client, user_a, rec["id"]).json()["analysis_id"]

    # not ready yet
    assert client.get(f"/api/v1/analysis/{aid}/status", headers=user_a.headers).json()["status"] == "QUEUED"
    not_ready = client.get(f"/api/v1/reports/{aid}", headers=user_a.headers)
    assert not_ready.status_code == 409
    assert not_ready.json()["error"]["code"] == "REPORT_NOT_READY"

    run_worker(aid)

    status = client.get(f"/api/v1/analysis/{aid}/status", headers=user_a.headers).json()
    assert status["status"] == "COMPLETED" and status["progress"] == 100

    report = client.get(f"/api/v1/reports/{aid}", headers=user_a.headers)
    assert report.status_code == 200
    body = report.json()
    assert body["is_simulated"] is True and body["analysis_mode"] == "mock"
    assert body["overall_score"] is not None
    assert len(body["metrics"]) >= 3
    # a metric that could not be measured is never listed with a score
    assert all(m["score"] is not None for m in body["metrics"])
    assert any(m["id"] == "pronunciation" for m in body["unavailable_metrics"])
    assert body["song"]["audio_url"] and "users/" not in body["song"]["audio_url"]


def test_worker_is_idempotent(client, user_a, upload_song, upload_recording, monkeypatch, db):
    monkeypatch.setattr("time.sleep", lambda s: None)
    _, rec = setup_take(client, user_a, upload_song, upload_recording)
    aid = start(client, user_a, rec["id"]).json()["analysis_id"]
    run_worker(aid)
    run_worker(aid)   # a redelivered task does nothing
    assert remaining(client, user_a) == 9


def test_failed_analysis_refunds_credit_once(client, user_a, upload_song, upload_recording, monkeypatch):
    def boom(db, analysis):
        raise RuntimeError("internal detail that must not leak")

    monkeypatch.setattr(analysis_worker, "run_pipeline", boom)
    _, rec = setup_take(client, user_a, upload_song, upload_recording)
    aid = start(client, user_a, rec["id"]).json()["analysis_id"]
    assert remaining(client, user_a) == 9

    run_worker(aid)

    status = client.get(f"/api/v1/analysis/{aid}/status", headers=user_a.headers).json()
    assert status["status"] == "FAILED"
    assert status["error"]["credit_refunded"] is True
    assert "internal detail" not in str(status)
    assert remaining(client, user_a) == 10

    analysis_worker._fail(uuid.UUID(aid), "ANALYSIS_FAILED", "again")   # a second refund attempt
    assert remaining(client, user_a) == 10


def test_ledger_has_one_charge_per_analysis(client, user_a, upload_song, upload_recording, db):
    _, rec = setup_take(client, user_a, upload_song, upload_recording)
    aid = start(client, user_a, rec["id"]).json()["analysis_id"]
    start(client, user_a, rec["id"])
    rows = db.scalars(
        select(CreditTransaction).where(CreditTransaction.reference_id == aid, CreditTransaction.amount == -1)
    ).all()
    assert len(rows) == 1


# ---------------- ownership of analyses and reports ----------------
def test_other_user_cannot_read_analysis_or_report(client, user_a, user_b, upload_song, upload_recording, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    _, rec = setup_take(client, user_a, upload_song, upload_recording)
    aid = start(client, user_a, rec["id"]).json()["analysis_id"]
    run_worker(aid)
    for path in (f"/api/v1/analysis/{aid}", f"/api/v1/analysis/{aid}/status", f"/api/v1/reports/{aid}"):
        assert client.get(path, headers=user_b.headers).status_code == 404, path
    assert client.delete(f"/api/v1/reports/{aid}", headers=user_b.headers).status_code == 404
    assert client.get("/api/v1/analysis", headers=user_b.headers).json()["total"] == 0


# ---------------- progress ----------------
def test_progress_tracks_attempts(client, user_a, upload_song, upload_recording, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    song = upload_song(user_a)

    empty = client.get("/api/v1/progress", headers=user_a.headers).json()
    assert empty["total_analyses"] == 0 and empty["average_score"] is None

    for _ in range(2):
        rec = upload_recording(user_a, song["id"])
        aid = start(client, user_a, rec["id"]).json()["analysis_id"]
        run_worker(aid)

    detail = client.get(f"/api/v1/progress/songs/{song['id']}", headers=user_a.headers).json()
    assert detail["attempt_count"] == 2
    assert [h["attempt"] for h in detail["history"]] == [1, 2]
    assert detail["improvement"] is not None

    overview = client.get("/api/v1/progress", headers=user_a.headers).json()
    assert overview["total_analyses"] == 2 and overview["songs_practiced"] == 1


def test_progress_for_someone_elses_song_is_404(client, user_a, user_b, upload_song):
    song = upload_song(user_a)
    assert client.get(f"/api/v1/progress/songs/{song['id']}", headers=user_b.headers).status_code == 404


# ---------------- usage ----------------
def test_usage_shape(client, user_a):
    body = client.get("/api/v1/usage", headers=user_a.headers).json()
    assert body["limit"] == 10 and body["remaining"] == 10 and body["used"] == 0
    assert body["can_analyze"] is True and body["upgrade_required"] is False


def test_deleting_report_removes_attempt(client, user_a, upload_song, upload_recording, monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    song, rec = setup_take(client, user_a, upload_song, upload_recording)
    aid = start(client, user_a, rec["id"]).json()["analysis_id"]
    run_worker(aid)
    assert client.delete(f"/api/v1/reports/{aid}", headers=user_a.headers).status_code == 200
    assert client.get(f"/api/v1/reports/{aid}", headers=user_a.headers).status_code == 404
    assert remaining(client, user_a) == 9   # a deleted report does not return the credit
