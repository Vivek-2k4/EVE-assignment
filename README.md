# EVE Diagnostics Booking API

**Submitted by:** Vivek Chandra Arya

Backend service for diagnostic test bookings with **simulated payments** and an **idempotent payment webhook**.

**Stack:** Python 3.12, Django 5 + Django REST Framework, SimpleJWT, PostgreSQL (SQLite fallback), drf-spectacular (Swagger), pytest, Docker.

## Run it

> **Tested:** the local SQLite setup below, the 78 automated tests, and the full booking → payment → webhook flow through Swagger.
> **Not tested:** the Docker / PostgreSQL setup. I did not have Docker installed on my machine, so `Dockerfile` and `docker-compose.yml` are written but have not been run.

### Local (SQLite, no setup needed)

```bash
git clone https://github.com/Vivek-2k4/EVE-assignment.git
cd EVE-assignment
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python manage.py migrate
python manage.py seed_demo         # demo centres and tests
python manage.py runserver
```

Then open **http://127.0.0.1:8000/api/docs/** (Swagger UI). The root URL redirects there.

Windows PowerShell may block the activation script. If so, run `Set-ExecutionPolicy -Scope Process Bypass` first (it only affects that window).

To create a staff user for managing centres and tests: `python manage.py createsuperuser`.

Set `DATABASE_URL=postgres://user:pass@host:5432/db` to use PostgreSQL locally. Copy `.env.example` for all settings.

### Docker (PostgreSQL), untested

```bash
docker compose up --build
docker compose exec web python manage.py seed_demo
docker compose exec web python manage.py createsuperuser
```

### Tests

```bash
pytest
```

78 tests, run on SQLite by default. Set `DATABASE_URL` to run the same suite against PostgreSQL.

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/auth/signup/` | none | Create account, returns JWT pair |
| POST | `/auth/login/` | none | Email + password, returns JWT pair |
| POST | `/auth/refresh/` | none | Refresh access token |
| GET | `/centres/` | none | List centres with tests and prices (`?location=`, `?test=<id>`, paginated) |
| POST/PATCH/DELETE | `/centres/`, `/centres/{id}/` | staff | Manage centres |
| GET | `/centres/{id}/tests/` | none | Tests offered by a centre |
| POST | `/centres/{id}/tests/` | staff | Offer a test at a price |
| GET/POST/PATCH/DELETE | `/tests/`, `/tests/{id}/` | read: none, write: staff | Test catalogue |
| POST | `/bookings/` | JWT | Create booking (status `PENDING`) |
| GET | `/bookings/`, `/bookings/{id}/` | JWT | Own bookings (`?status=`) |
| POST | `/bookings/{id}/cancel/` | JWT | Cancel a PENDING or CONFIRMED booking |
| POST | `/payments/` | JWT | Simulated payment, SUCCESS or FAILED, updates the booking |
| POST | `/payments/webhook/` | HMAC signature | Provider status update (idempotent) |

Interactive docs: `/api/docs/` (Swagger UI), `/api/schema/` (OpenAPI schema).
In Swagger, click **Authorize** and paste only the `access` token (Swagger adds "Bearer" itself). Access tokens last 30 minutes; log in again for a fresh one.

### Example flow

These examples use `curl` and a shell script, so run them in Mac/Linux/Git Bash. **On Windows PowerShell, use Swagger at `/api/docs/` instead** (see the PowerShell webhook example below).

```bash
# 1. Sign up
curl -s -X POST localhost:8000/auth/signup/ -H 'Content-Type: application/json' \
  -d '{"email":"alice@example.com","password":"S3cure-pass-phrase!","full_name":"Alice"}'
# -> {"user": {...}, "access": "<JWT>", "refresh": "<JWT>"}

# 2. Browse
curl -s localhost:8000/centres/

# 3. Book (centre_id/test_id from step 2)
curl -s -X POST localhost:8000/bookings/ -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' \
  -d '{"centre_id":1,"test_id":1,"appointment_at":"2026-12-01T10:00:00+05:30"}'
# -> 201 {"id":"<uuid>","status":"PENDING","amount":"350.00",...}

# 4a. Pay synchronously (random outcome; add "simulate":"SUCCESS"|"FAILED" to force one)
curl -s -X POST localhost:8000/payments/ -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: pay-001' -d '{"booking_id":"<uuid>"}'
# -> 201 {"status":"SUCCESS","provider_reference":"sim_...","amount":"350.00",...}; booking -> CONFIRMED (or FAILED)

# 4b. ...or defer, and let the webhook settle it
curl -s -X POST localhost:8000/payments/ -H "Authorization: Bearer $ACCESS" -H 'Content-Type: application/json' \
  -d '{"booking_id":"<uuid>","deferred":true}'            # payment PENDING
scripts/send_webhook.sh evt_001 sim_xxxxxxxx SUCCESS        # signs + sends the webhook
scripts/send_webhook.sh evt_001 sim_xxxxxxxx SUCCESS        # replay -> {"status":"duplicate",...}, no state change
```

Note: `simulate` and `deferred` cannot be combined (`simulate` settles immediately, `deferred` waits for the webhook).

### Webhook contract

`POST /payments/webhook/` with header `X-Signature: hex(HMAC_SHA256(WEBHOOK_SECRET, raw_body))`:

```json
{"event_id": "evt_001", "provider_reference": "sim_...", "status": "SUCCESS"}
```

Responses: `200 {"status":"processed"|"duplicate","outcome":"..."}`, `400` bad payload, `401` bad or missing signature, `404` unknown payment reference.

**PowerShell example** (default secret `dev-webhook-secret`; paste the real `provider_reference`):

```powershell
$secret = "dev-webhook-secret"
$body = '{"event_id":"evt_001","provider_reference":"sim_PASTE_HERE","status":"SUCCESS"}'
$h = New-Object System.Security.Cryptography.HMACSHA256
$h.Key = [Text.Encoding]::UTF8.GetBytes($secret)
$sig = ($h.ComputeHash([Text.Encoding]::UTF8.GetBytes($body)) | ForEach-Object { $_.ToString("x2") }) -join ""
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/payments/webhook/ -ContentType "application/json" -Headers @{ "X-Signature" = $sig } -Body $body
```

Run the last line twice: the first call returns `processed`, the replay returns `duplicate`.

### Error format

Every error is `{"error": {"code": "...", "message": "...", "details": {...}}}` (`details` only for validation errors).

## Database design

```
User 1─* Booking *─1 CentreTest *─1 Centre
                        │ *─1 DiagnosticTest
Booking 1─1 Payment 1─* WebhookEvent
```

| Table | Notes |
|---|---|
| `Centre` | name, location (indexed). Unique (name, location). |
| `DiagnosticTest` | name (unique), description. |
| `CentreTest` | centre × test with **price** (price varies per centre). Unique (centre, test); `price > 0` check. |
| `Booking` | UUID pk, user, centre_test, appointment_at, **amount (price snapshot)**, status. Partial unique index on (user, centre_test, appointment_at) while status is PENDING/CONFIRMED prevents double-booking. |
| `Payment` | UUID pk, **OneToOne booking**, amount, status, unique `provider_reference`, optional `idempotency_key`. |
| `WebhookEvent` | **Unique `event_id`** is the idempotency ledger; stores payload and processing outcome. |

## Design decisions

- **Booking state machine** lives in one place (`Booking.ALLOWED_TRANSITIONS`): `PENDING → CONFIRMED | FAILED | CANCELLED`, `CONFIRMED → CANCELLED`. `FAILED` and `CANCELLED` are terminal, so late or out-of-order events can't flip a booking.
- **Webhook idempotency:** inside one `transaction.atomic()` the service inserts the `WebhookEvent` (unique `event_id`), locks the payment and booking rows with `select_for_update`, then applies the change. A replay finds the existing event and returns `200 duplicate` (with the original outcome) without touching anything. If processing fails (for example an unknown payment) the event row rolls back with it, so the provider's retry is handled normally. A *different* event that contradicts a settled payment (for example FAILED after SUCCESS) is recorded but ignored (`ignored_conflict`).
- **Webhook authenticity:** HMAC-SHA256 over the raw body with constant-time comparison.
- **Payments:** `POST /payments/` locks the booking row, requires it to belong to the caller and be `PENDING`, and creates exactly one payment (OneToOne plus `Idempotency-Key` replay support). `simulate` forces an outcome so tests and demos are deterministic; disable it with `PAYMENT_ALLOW_SIMULATE=false`.
- **Authorization:** querysets are scoped to `request.user`, so another user's booking returns `404` (existence isn't leaked). Catalogue writes are staff-only.
- **Validation:** past appointment dates, tests not offered at the chosen centre, malformed IDs and duplicate active slots are all rejected with clear errors.
- **Rate limiting:** signup and login are throttled (`AUTH_THROTTLE_RATE`, default 20/min per IP).
- **Logging:** JSON lines for booking, payment and webhook events (`common/logging.py`).

## Assumptions

- Email is the login identifier (stored as the Django username, lowercased).
- The amount is taken from the centre's current price at booking time; clients can't set amount or status.
- One payment per booking. A FAILED payment fails the booking; the user books again to retry.
- Appointments must be in the future; there is no slot-capacity model (a centre can take any number of bookings per slot).
- Cancelling a CONFIRMED booking does not refund (no refund flow in scope).
- The webhook identifies payments by the `provider_reference` returned from `POST /payments/`.
- Tests use SQLite, which ignores `select_for_update`; the row-locking behaviour applies on PostgreSQL and is not covered by the test-suite.
- Defaults such as `SECRET_KEY`, `WEBHOOK_SECRET` and `PAYMENT_ALLOW_SIMULATE=true` are for local development only; set real values for any deployment.

## What I'd improve with more time

- Run the Docker/PostgreSQL setup and add real concurrency tests against PostgreSQL in CI (parallel duplicate webhooks, pay vs. cancel races).
- Refund flow for cancelled/confirmed bookings, and alerting on `payment_updated_booking_unchanged` outcomes.
- Webhook timestamp in the signature to bound replay windows; secret rotation.
- Slot capacity and centre opening hours; reminders via Celery.
- Redis-backed throttling and caching of the centre catalogue.
- Retry queue / dead-letter handling for failed webhook processing; request-ID logging middleware.
- Per-centre-test price history and soft-delete for catalogue entries.