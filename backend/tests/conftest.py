"""
NAADAMAYA test setup.

Run the tests inside the API container (it has the database and FFmpeg):

    docker compose exec api pytest -q

What this file does:
  1. Sets test environment variables BEFORE the app is imported (settings are
     read once at import). Mock OTP and mock analysis, rate limiting off,
     and a throwaway upload folder.
  2. Creates a separate test database (name must end in "_test") and builds the
     tables from the models. Your development database is never touched.
  3. Before every test: empties all tables and re-adds the FREE, GO and PRO plans.
  4. Replaces the Celery task with a fake, so no test needs Redis or a worker.

Tests build the schema from the models (create_all), NOT from the Alembic
migration, so they do not prove the migration is correct.
"""

import io
import os
import sys
import tempfile
import uuid
from pathlib import Path

# ---- 1. environment, before anything from `app` is imported ----
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://naadamaya:naadamaya@db:5432/naadamaya_test",
)
_UPLOAD_DIR = tempfile.mkdtemp(prefix="naadamaya-test-uploads-")

os.environ.update(
    {
        "ENVIRONMENT": "development",
        "DEBUG": "false",
        "DATABASE_URL": TEST_DATABASE_URL,
        "JWT_SECRET": "test-jwt-secret-test-jwt-secret-test-jwt-secret-1234",
        "TOKEN_HASH_SECRET": "test-hash-secret-test-hash-secret-test-hash-5678",
        "OTP_MODE": "development",
        "OTP_PROVIDER": "mock",
        "OTP_DEV_FIXED_CODE": "123456",
        "OTP_RESEND_COOLDOWN_SECONDS": "0",
        "OTP_MAX_REQUESTS_PER_HOUR": "1000",
        "RATE_LIMIT_OTP_PER_IP_PER_HOUR": "1000",
        "RATE_LIMIT_ENABLED": "false",
        "ANALYSIS_MODE": "mock",
        "STORAGE_PROVIDER": "local",
        "STORAGE_LOCAL_DIR": _UPLOAD_DIR,
        "RAZORPAY_KEY_ID": "rzp_test_key",
        "RAZORPAY_KEY_SECRET": "test_razorpay_secret",
        "RAZORPAY_WEBHOOK_SECRET": "test_webhook_secret",
    }
)

import numpy as np  # noqa: E402
import pytest  # noqa: E402
import soundfile as sf  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402


# ---- 2. the test database ----
def _ensure_test_database() -> None:
    url = make_url(TEST_DATABASE_URL)
    if not (url.database or "").endswith("_test"):
        raise RuntimeError("TEST_DATABASE_URL must point at a database whose name ends in '_test'.")
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": url.database})
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()


_ensure_test_database()

from app.core.database import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402
from app.services.plans.plan_service import ensure_default_plans  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_database(_schema):
    """Empty every table, then add the three plans, before each test."""
    names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    with SessionLocal() as db:
        ensure_default_plans(db)
        db.commit()
    yield


# ---- 4. no Redis, no worker ----
class _FakeTask:
    def __init__(self):
        self.id = uuid.uuid4().hex


class _FakeRunAnalysis:
    """Stands in for the Celery task. Records what was queued."""

    def __init__(self):
        self.calls: list[dict] = []
        self.fail = False

    def apply_async(self, args=None, queue=None, **kwargs):
        if self.fail:
            raise ConnectionError("broker down")
        self.calls.append({"args": args, "queue": queue})
        return _FakeTask()


@pytest.fixture(autouse=True)
def queued_tasks(monkeypatch) -> _FakeRunAnalysis:
    fake = _FakeRunAnalysis()
    monkeypatch.setattr("app.services.analysis.analysis_service.run_analysis", fake)
    return fake


# ---- clients and sessions ----
@pytest.fixture()
def client() -> TestClient:
    # raise_server_exceptions=False so a crash shows up as the real 500 JSON response
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture()
def db():
    with SessionLocal() as session:
        yield session
        session.rollback()


# ---- signing in ----
def phone_number(n: int = 1) -> str:
    """A distinct valid Indian mobile number per n (n up to 99999)."""
    return f"+9198765{n:05d}"


class Account:
    def __init__(self, data: dict, phone: str):
        self.phone = phone
        self.data = data
        self.user_id = data["user"]["id"]
        self.access_token = data["access_token"]
        self.refresh_token = data["refresh_token"]
        self.headers = {"Authorization": f"Bearer {self.access_token}"}


@pytest.fixture()
def login(client):
    """login(n) signs in the n-th test phone number (creating the account on first use)."""

    def _login(n: int = 1) -> Account:
        phone = phone_number(n)
        sent = client.post("/api/v1/auth/send-otp", json={"phone_number": phone})
        assert sent.status_code == 200, sent.text
        verified = client.post(
            "/api/v1/auth/verify-otp", json={"phone_number": phone, "otp": "123456"}
        )
        assert verified.status_code == 200, verified.text
        return Account(verified.json(), phone)

    return _login


@pytest.fixture()
def user_a(login) -> Account:
    return login(1)


@pytest.fixture()
def user_b(login) -> Account:
    return login(2)


# ---- audio ----
def make_wav(seconds: float = 5.0, freq: float = 220.0, sample_rate: int = 22050) -> bytes:
    """A short voice-like tone (a gentle vibrato on a steady note). Real audio, so FFmpeg accepts it."""
    t = np.arange(int(seconds * sample_rate)) / sample_rate
    phase = 2 * np.pi * freq * t + 3.0 * np.sin(2 * np.pi * 5.5 * t)
    signal = 0.4 * np.sin(phase) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.7 * t))
    buffer = io.BytesIO()
    sf.write(buffer, signal.astype("float32"), sample_rate, format="WAV", subtype="PCM_16")
    return buffer.getvalue()


@pytest.fixture()
def wav_bytes() -> bytes:
    return make_wav()


@pytest.fixture()
def upload_song(client, wav_bytes):
    def _upload(account: Account, title: str = "Test Song") -> dict:
        response = client.post(
            "/api/v1/songs/reference",
            headers=account.headers,
            files={"file": ("original.wav", wav_bytes, "audio/wav")},
            data={"title": title, "artist": "Test Artist"},
        )
        assert response.status_code == 201, response.text
        return response.json()

    return _upload


@pytest.fixture()
def upload_recording(client, wav_bytes):
    def _upload(account: Account, song_id: str, source: str = "upload") -> dict:
        response = client.post(
            "/api/v1/recordings",
            headers=account.headers,
            files={"file": ("take.wav", wav_bytes, "audio/wav")},
            data={"song_id": song_id, "source": source},
        )
        assert response.status_code == 201, response.text
        return response.json()

    return _upload
