import json

import pytest

from bookings.models import Booking
from payments.models import Payment, WebhookEvent
from payments.signature import compute_signature

pytestmark = pytest.mark.django_db


def send(api, payload, signature=None, raw=None):
    body = raw if raw is not None else json.dumps(payload)
    sig = signature if signature is not None else compute_signature(body.encode())
    return api.post("/payments/webhook/", data=body, content_type="application/json", HTTP_X_SIGNATURE=sig)


@pytest.fixture
def pending_payment(user_api, booking):
    r = user_api.post("/payments/", {"booking_id": str(booking.id), "deferred": True}, format="json")
    return Payment.objects.get(pk=r.data["id"])


def event(payment, status="SUCCESS", event_id="evt_1"):
    return {"event_id": event_id, "provider_reference": payment.provider_reference, "status": status}


def test_success_webhook_confirms_booking(anon_api, pending_payment):
    r = send(anon_api, event(pending_payment))
    assert r.status_code == 200 and r.data == {"status": "processed", "outcome": "applied"}
    pending_payment.refresh_from_db()
    assert pending_payment.status == "SUCCESS"
    assert pending_payment.booking.status == "CONFIRMED"


def test_failed_webhook_fails_booking(anon_api, pending_payment):
    send(anon_api, event(pending_payment, "FAILED"))
    pending_payment.refresh_from_db()
    assert pending_payment.status == "FAILED" and pending_payment.booking.status == "FAILED"


def test_replayed_event_is_idempotent(anon_api, pending_payment):
    payload = event(pending_payment)
    results = [send(anon_api, payload) for _ in range(3)]
    assert [r.status_code for r in results] == [200, 200, 200]
    assert [r.data["status"] for r in results] == ["processed", "duplicate", "duplicate"]
    assert WebhookEvent.objects.count() == 1
    assert Payment.objects.count() == 1 and Booking.objects.count() == 1
    pending_payment.refresh_from_db()
    assert pending_payment.booking.status == "CONFIRMED"


def test_replay_does_not_undo_later_state(anon_api, pending_payment, user_api):
    payload = event(pending_payment)
    send(anon_api, payload)
    user_api.post(f"/bookings/{pending_payment.booking_id}/cancel/")
    send(anon_api, payload)  # stale replay of the original success
    pending_payment.booking.refresh_from_db()
    assert pending_payment.booking.status == "CANCELLED"


def test_conflicting_event_does_not_flip_settled_payment(anon_api, pending_payment):
    send(anon_api, event(pending_payment, "SUCCESS", "evt_a"))
    r = send(anon_api, event(pending_payment, "FAILED", "evt_b"))
    assert r.status_code == 200 and r.data["outcome"] == "ignored_conflict"
    pending_payment.refresh_from_db()
    assert pending_payment.status == "SUCCESS" and pending_payment.booking.status == "CONFIRMED"


def test_different_event_same_status_is_noop(anon_api, pending_payment):
    send(anon_api, event(pending_payment, "SUCCESS", "evt_a"))
    r = send(anon_api, event(pending_payment, "SUCCESS", "evt_b"))
    assert r.data["outcome"] == "noop_already_in_state"
    assert WebhookEvent.objects.count() == 2


def test_webhook_after_user_cancelled_does_not_resurrect_booking(anon_api, pending_payment, user_api):
    user_api.post(f"/bookings/{pending_payment.booking_id}/cancel/")
    r = send(anon_api, event(pending_payment))
    assert r.data["outcome"] == "payment_updated_booking_unchanged"
    pending_payment.booking.refresh_from_db()
    assert pending_payment.booking.status == "CANCELLED"


def test_webhook_for_sync_payment_is_noop(anon_api, user_api, booking):
    p = user_api.post("/payments/", {"booking_id": str(booking.id), "simulate": "SUCCESS"}, format="json")
    r = send(anon_api, {"event_id": "e1", "provider_reference": p.data["provider_reference"], "status": "SUCCESS"})
    assert r.data["outcome"] == "noop_already_in_state"


def test_unknown_payment_reference_is_404_and_event_not_recorded(anon_api, pending_payment):
    r = send(anon_api, {"event_id": "evt_x", "provider_reference": "sim_missing", "status": "SUCCESS"})
    assert r.status_code == 404
    assert WebhookEvent.objects.count() == 0  # provider can safely retry later


def test_missing_or_bad_signature_rejected(anon_api, pending_payment):
    payload = event(pending_payment)
    assert send(anon_api, payload, signature="deadbeef").status_code == 401
    r = anon_api.post("/payments/webhook/", data=json.dumps(payload), content_type="application/json")
    assert r.status_code == 401
    pending_payment.refresh_from_db()
    assert pending_payment.status == "PENDING" and WebhookEvent.objects.count() == 0


def test_signature_covers_exact_body(anon_api, pending_payment):
    body = json.dumps(event(pending_payment))
    sig = compute_signature(body.encode())
    tampered = body.replace("SUCCESS", "FAILED")
    assert send(anon_api, None, signature=sig, raw=tampered).status_code == 401


@pytest.mark.parametrize(
    "raw",
    ["not json", "[1, 2]", '{"event_id": "x"}', '{"event_id": "x", "provider_reference": "y", "status": "PENDING"}'],
)
def test_invalid_payloads_rejected(anon_api, raw):
    assert send(anon_api, None, raw=raw).status_code == 400


def test_webhook_does_not_require_jwt(anon_api, pending_payment):
    assert send(anon_api, event(pending_payment)).status_code == 200
