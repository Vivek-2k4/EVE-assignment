import pytest

from bookings.models import Booking
from payments.models import Payment

pytestmark = pytest.mark.django_db


def _pay(api, booking, **extra):
    headers = extra.pop("headers", {})
    return api.post("/payments/", {"booking_id": str(booking.id), **extra}, format="json", **headers)


def test_successful_payment_confirms_booking(user_api, booking):
    r = _pay(user_api, booking, simulate="SUCCESS")
    assert r.status_code == 201
    assert r.data["status"] == "SUCCESS" and r.data["amount"] == "600.00"
    assert r.data["provider_reference"].startswith("sim_")
    booking.refresh_from_db()
    assert booking.status == "CONFIRMED"


def test_failed_payment_marks_booking_failed(user_api, booking):
    r = _pay(user_api, booking, simulate="FAILED")
    assert r.status_code == 201 and r.data["status"] == "FAILED"
    booking.refresh_from_db()
    assert booking.status == "FAILED"


def test_random_outcome_is_one_of_two_and_consistent(user_api, booking):
    r = _pay(user_api, booking)
    assert r.data["status"] in {"SUCCESS", "FAILED"}
    booking.refresh_from_db()
    assert booking.status == {"SUCCESS": "CONFIRMED", "FAILED": "FAILED"}[r.data["status"]]


def test_cannot_pay_twice(user_api, booking):
    assert _pay(user_api, booking, simulate="SUCCESS").status_code == 201
    assert _pay(user_api, booking, simulate="SUCCESS").status_code == 409
    assert Payment.objects.count() == 1


def test_failed_booking_cannot_be_repaid(user_api, booking):
    _pay(user_api, booking, simulate="FAILED")
    assert _pay(user_api, booking, simulate="SUCCESS").status_code == 409


def test_idempotency_key_replay_returns_original(user_api, booking):
    headers = {"headers": {"HTTP_IDEMPOTENCY_KEY": "key-123"}}
    first = _pay(user_api, booking, simulate="SUCCESS", **headers)
    second = _pay(user_api, booking, simulate="SUCCESS", **headers)
    assert first.status_code == 201 and second.status_code == 200
    assert first.data["id"] == second.data["id"]
    assert Payment.objects.count() == 1


def test_different_idempotency_key_is_a_conflict(user_api, booking):
    _pay(user_api, booking, simulate="SUCCESS", headers={"HTTP_IDEMPOTENCY_KEY": "a"})
    r = _pay(user_api, booking, simulate="SUCCESS", headers={"HTTP_IDEMPOTENCY_KEY": "b"})
    assert r.status_code == 409


def test_cannot_pay_cancelled_booking(user_api, booking):
    user_api.post(f"/bookings/{booking.id}/cancel/")
    assert _pay(user_api, booking, simulate="SUCCESS").status_code == 409
    assert Payment.objects.count() == 0


def test_cannot_pay_for_someone_elses_booking(other_api, booking):
    assert _pay(other_api, booking, simulate="SUCCESS").status_code == 404
    booking.refresh_from_db()
    assert booking.status == "PENDING" and Payment.objects.count() == 0


def test_unknown_and_malformed_booking_ids(user_api):
    assert user_api.post("/payments/", {"booking_id": "00000000-0000-0000-0000-000000000000"}, format="json").status_code == 404
    assert user_api.post("/payments/", {"booking_id": "nope"}, format="json").status_code == 400
    assert user_api.post("/payments/", {}, format="json").status_code == 400


def test_invalid_simulate_value(user_api, booking):
    assert _pay(user_api, booking, simulate="MAYBE").status_code == 400


def test_simulate_can_be_disabled(user_api, booking, settings):
    settings.PAYMENT_ALLOW_SIMULATE = False
    assert _pay(user_api, booking, simulate="SUCCESS").status_code == 400


def test_deferred_payment_stays_pending(user_api, booking):
    r = _pay(user_api, booking, deferred=True)
    assert r.status_code == 201 and r.data["status"] == "PENDING"
    booking.refresh_from_db()
    assert booking.status == "PENDING"
    assert isinstance(Booking.objects.get(pk=booking.pk).payment, Payment)
