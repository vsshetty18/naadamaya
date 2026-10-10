# NAADAMAYA backend

**sing. evolve. globally.**

FastAPI + PostgreSQL + Redis + Celery. Sign-in is phone number + OTP. Payments use Razorpay. Audio analysis runs in a background worker.

## Start everything (Docker)

```bash
cp .env.example .env          # then fill in the secrets (see below)
docker compose up --build
```

This starts PostgreSQL, Redis, the API (applies migrations on start) and the analysis worker.

- API: http://localhost:8000
- Swagger docs: http://localhost:8000/docs (not served when `ENVIRONMENT=production`)
- Health: `/health`, `/health/db`, `/health/redis`

Generate each secret with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

You need different values for `JWT_SECRET` and `TOKEN_HASH_SECRET`.

## Development sign-in (no SMS provider)

With `OTP_MODE=development` and `OTP_PROVIDER=mock`:

1. `POST /api/v1/auth/send-otp` with `{"phone_number": "+919876543210"}`
2. `POST /api/v1/auth/verify-otp` with the same number and the code `123456` (`OTP_DEV_FIXED_CODE`)

The development code is returned in `development_otp` only outside production. Production refuses to start with mock OTP.

## Analysis modes

| `ANALYSIS_MODE` | What happens |
|---|---|
| `mock` | Nothing is measured. Clearly labelled simulated results (`is_simulated: true`) for frontend development. **Refused in production.** |
| `real` | The real pipeline: pYIN pitch, DTW alignment, pitch, melody, rhythm, stability, expression and breath analyzers. |

Honest limits of the real pipeline:

- **No speech recogniser exists.** Pronunciation is always reported as unavailable. Nothing is estimated.
- Pitch tracking follows ONE dominant pitch. On a reference with instruments it may follow an instrument. Weak data gives "insufficient data", not a made-up score.
- Section names are generic ("Section 1"), marked `is_estimated`.
- Key and tempo are estimates and are left out when unclear.
- All thresholds are untested starting values. Tune them on real recordings.

## Make yourself an admin

There is no API for this. In the database:

```sql
UPDATE users SET role = 'ADMIN' WHERE id = '<your user id>';
```

## Razorpay

Set `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` and `RAZORPAY_WEBHOOK_SECRET`. In the Razorpay dashboard add a webhook:

- URL: `https://<your-api>/api/v1/webhooks/razorpay`
- Secret: the same as `RAZORPAY_WEBHOOK_SECRET`
- Events: `payment.captured`, `payment.failed`

The price always comes from the `plans` table. Only `RAZORPAY_KEY_ID` is ever sent to the frontend.

## Fixes that must be applied (earlier files)

If these are not applied the API will fail or misbehave:

1. `analyzers/interfaces.py`: add `details: dict[str, Any] = field(default_factory=dict)` to `AlignmentResult`.
2. `services/payments/payment_service.py`: import `get_active_subscription` and replace the `activate_paid_plan.__globals__[...]` line with a normal call.
3. `services/credits/credit_service.py`: replace the `get_usage` "recent" query with the simpler version given earlier.
4. `docker-compose.yml`: add `-Q analysis_priority,analysis` to the worker command.
5. Optional: in `schemas/report.py`, change the `PitchAxisNote.value` description to "MIDI note number".

## Production checklist

- `ENVIRONMENT=production`, `DEBUG=false`, `OTP_MODE=production`, a real `OTP_PROVIDER`, `ANALYSIS_MODE=real`.
- Exact `CORS_ORIGINS` (no `*`).
- `STORAGE_PROVIDER=s3` with a PRIVATE bucket.
- Serve over HTTPS. Behind a proxy, run uvicorn with `--proxy-headers` and set `TRUST_PROXY_HEADERS=true` so rate limits see real client IPs.
- Remove `--reload` and the `.:/app` mount from `docker-compose.yml`.
- Use real database credentials, not the development ones.
- Schedule `POST /api/v1/admin/maintenance/fail-stuck` (fails and refunds analyses stuck over 30 minutes).

## Layout

```
app/
  core/         config, database, security, logging, exceptions
  models/       17 tables
  schemas/      request and response shapes
  api/v1/       routes
  services/     auth, otp, payments, plans, subscriptions, credits,
                storage, audio, analysis, progress, dashboard, profile, account
  analyzers/    replaceable analysis modules (interfaces.py is the contract)
  middleware/   request id, logging, security headers, rate limit, errors
  workers/      Celery app and the analysis task
alembic/        migrations (0001 creates all tables and seeds FREE, GO, PRO)
```

## Not built

Instagram/YouTube integration, AI music teacher, song recommendations, vocal separation, structure labelling (Verse/Chorus), a speech recogniser, Razorpay recurring subscriptions, changing the phone number, HTTP Range on local audio streaming.
