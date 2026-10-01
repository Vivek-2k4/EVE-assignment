# EVE Diagnostics Booking API

Backend service for diagnostic test bookings with **simulated payments** and an **idempotent payment webhook**.

**Stack:** Python 3.12, Django 5 + Django REST Framework, SimpleJWT, PostgreSQL (SQLite fallback), drf-spectacular (Swagger), pytest, Docker.

## Run it

### Docker (PostgreSQL)
```bash
docker compose up --build
docker compose exec web python manage.py seed_demo          # demo centres/tests
docker compose exec web python manage.py createsuperuser    # to manage the catalogue via /admin or API
```
API: http://localhost:8000 · Swagger UI: http://localhost:8000/api/docs/

### Local (SQLite, no setup)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```
Set `DATABASE_URL=postgres://user:pass@host:5432/db` to use PostgreSQL locally. Copy `.env.example` for all settings.

### Tests
```bash
pytest
```
Runs on SQLite by default; set `DATABASE_URL` to run the same suite against PostgreSQL.

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/auth/signup/` | – | Create account, returns JWT pair |
| POST | `/auth/login/` | – | Email + password → JWT pair |
| POST | `/auth/refresh/` | – | Refresh access token |
| GET | `/centres/` | – | List centres with tests & prices (`?location=`, `?test=<id>`, paginated) |
| POST/PATCH/DELETE | `/centres/` , `/centres/{id}/` | staff | Manage centres |
| GET | `/centres/{id}/tests/` | – | Tests offered by a centre |
| POST | `/centres/{id}/tests/` | staff | Offer a test at a price |
| GET/POST/... | `/tests/` | read: –, write: staff | Test catalogue |
| POST | `/bookings/` | JWT | Create booking (status `PENDING`) |
| GET | `/bookings/`, `/bookings/{id}/` | JWT | Own bookings (`?status=`) |
| POST | `/bookings/{id}/cancel/` | JWT | Cancel a PENDING/CONFIRMED booking |
| POST | `/payments/` | JWT | Simulated payment → SUCCESS/FAILED, updates booking |
| POST | `/payments/webhook/` | HMAC signature | Provider status update (idempotent) |

### Example flow
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

### Webhook contract
`POST /payments/webhook/` with header `X-Signature: hex(HMAC_SHA256(WEBHOOK_SECRET, raw_body))`:
```json
{"event_id": "evt_001", "provider_reference": "sim_...", "status": "SUCCESS"}
```
Responses: `200 {"status":"processed"|"duplicate","outcome":"..."}`, `400` bad payload, `401` bad/missing signature, `404` unknown payment reference.

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
| `WebhookEvent` | **Unique `event_id`** = idempotency ledger; stores payload and processing outcome. |

## Design decisions

- **Booking state machine** lives in one place (`Booking.ALLOWED_TRANSITIONS`): `PENDING → CONFIRMED|FAILED|CANCELLED`, `CONFIRMED → CANCELLED`. `FAILED` and `CANCELLED` are terminal, so late or out-of-order events can't flip a booking.
- **Webhook idempotency:** inside one `transaction.atomic()` the service inserts the `WebhookEvent` (unique `event_id`), locks the payment and booking rows with `select_for_update`, then applies the change. A replay finds the existing event and returns `200 duplicate` without touching anything. If processing fails (e.g. unknown payment) the event row rolls back with it, so the provider's retry is handled normally. A *different* event contradicting a settled payment (e.g. FAILED after SUCCESS) is recorded but ignored (`ignored_conflict`).
- **Webhook authenticity:** HMAC-SHA256 over the raw body with constant-time comparison.
- **Payments:** `POST /payments/` locks the booking row, requires it to be the caller's and `PENDING`, and creates exactly one payment (OneToOne + `Idempotency-Key` replay support). `simulate` forces an outcome so tests and demos are deterministic; disable with `PAYMENT_ALLOW_SIMULATE=false`.
- **Authorization:** querysets are scoped to `request.user`, so another user's booking is a `404` (doesn't leak existence). Catalogue writes are staff-only.
- **Rate limiting:** signup/login throttled (`AUTH_THROTTLE_RATE`, default 20/min per IP).
- **Logging:** JSON lines for booking/payment/webhook events (`common/logging.py`).

## Assumptions
- Email is the login identifier (stored as the Django username, lowercased).
- Amount is taken from the centre's current price at booking time; clients can't set amount or status.
- One payment per booking. A FAILED payment fails the booking; the user books again to retry.
- Appointments must be in the future; no slot-capacity model (a centre can take any number of bookings per slot).
- Cancelling a CONFIRMED booking doesn't refund (no refund flow in scope).
- The webhook identifies payments by `provider_reference` returned from `POST /payments/`.
- Tests use SQLite, which ignores `select_for_update`; row-locking behaviour applies on PostgreSQL.

## What I'd improve with more time
- Real concurrency tests against PostgreSQL (parallel duplicate webhooks, pay vs. cancel races) in CI.
- Refund flow for cancelled/confirmed bookings, and alerting on `payment_updated_booking_unchanged` outcomes.
- Webhook timestamp in the signature to bound replay windows; secret rotation.
- Slot capacity and centre opening hours; reminders via Celery.
- Redis-backed throttling and caching of the centre catalogue.
- Retry queue / dead-letter handling for failed webhook processing; request-ID logging middleware.
- Per-centre-test price history and soft-delete for catalogue entries.
