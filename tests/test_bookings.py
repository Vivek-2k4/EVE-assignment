from datetime import timedelta

import pytest
from django.utils import timezone

from bookings.models import Booking

pytestmark = pytest.mark.django_db


def _payload(centre_test, when):
    return {"centre_id": centre_test.centre_id, "test_id": centre_test.test_id, "appointment_at": when}


def test_create_booking_snapshots_price(user_api, centre_test, future_iso):
    r = user_api.post("/bookings/", _payload(centre_test, future_iso), format="json")
    assert r.status_code == 201
    assert r.data["status"] == "PENDING"
    assert r.data["amount"] == "600.00"
    assert r.data["centre"]["name"] == "EVE Karol Bagh"
    # Later price changes don't touch existing bookings.
    centre_test.price = 999
    centre_test.save()
    assert user_api.get(f"/bookings/{r.data['id']}/").data["amount"] == "600.00"


def test_booking_requires_auth(anon_api, centre_test, future_iso):
    assert anon_api.post("/bookings/", _payload(centre_test, future_iso), format="json").status_code == 401


def test_past_appointment_rejected(user_api, centre_test):
    past = (timezone.now() - timedelta(hours=1)).isoformat()
    r = user_api.post("/bookings/", _payload(centre_test, past), format="json")
    assert r.status_code == 400 and "appointment_at" in r.data["error"]["details"]


def test_test_not_offered_at_centre(user_api, centre_test, future_iso):
    from catalog.models import DiagnosticTest

    other = DiagnosticTest.objects.create(name="MRI")
    r = user_api.post("/bookings/", {**_payload(centre_test, future_iso), "test_id": other.id}, format="json")
    assert r.status_code == 400 and "test_id" in r.data["error"]["details"]


@pytest.mark.parametrize("field", ["centre_id", "test_id", "appointment_at"])
def test_missing_fields_rejected(user_api, centre_test, future_iso, field):
    body = _payload(centre_test, future_iso)
    body.pop(field)
    assert user_api.post("/bookings/", body, format="json").status_code == 400


def test_unknown_centre_rejected(user_api, centre_test, future_iso):
    r = user_api.post("/bookings/", {**_payload(centre_test, future_iso), "centre_id": 9999}, format="json")
    assert r.status_code == 400


def test_duplicate_active_slot_conflicts_but_allowed_after_cancel(user_api, centre_test, future_iso):
    first = user_api.post("/bookings/", _payload(centre_test, future_iso), format="json")
    assert user_api.post("/bookings/", _payload(centre_test, future_iso), format="json").status_code == 409
    user_api.post(f"/bookings/{first.data['id']}/cancel/")
    assert user_api.post("/bookings/", _payload(centre_test, future_iso), format="json").status_code == 201


def test_users_only_see_their_own_bookings(user_api, other_api, booking):
    assert user_api.get("/bookings/").data["count"] == 1
    assert other_api.get("/bookings/").data["count"] == 0


def test_other_users_booking_is_404_not_403(other_api, booking):
    assert other_api.get(f"/bookings/{booking.id}/").status_code == 404
    assert other_api.post(f"/bookings/{booking.id}/cancel/").status_code == 404
    booking.refresh_from_db()
    assert booking.status == "PENDING"


def test_malformed_and_unknown_booking_ids(user_api):
    assert user_api.get("/bookings/not-a-uuid/").status_code == 404
    assert user_api.get("/bookings/00000000-0000-0000-0000-000000000000/").status_code == 404


def test_cancel_then_cancel_again(user_api, booking):
    r = user_api.post(f"/bookings/{booking.id}/cancel/")
    assert r.status_code == 200 and r.data["status"] == "CANCELLED"
    assert user_api.post(f"/bookings/{booking.id}/cancel/").status_code == 409


def test_cannot_cancel_failed_booking(user_api, make_booking, user):
    b = make_booking(user, status=Booking.Status.FAILED)
    assert user_api.post(f"/bookings/{b.id}/cancel/").status_code == 409


def test_status_filter(user_api, booking):
    assert user_api.get("/bookings/?status=pending").data["count"] == 1
    assert user_api.get("/bookings/?status=CANCELLED").data["count"] == 0
    assert user_api.get("/bookings/?status=bogus").status_code == 400


def test_clients_cannot_set_status_or_amount(user_api, centre_test, future_iso):
    body = {**_payload(centre_test, future_iso), "status": "CONFIRMED", "amount": "1.00"}
    r = user_api.post("/bookings/", body, format="json")
    assert r.status_code == 201
    assert r.data["status"] == "PENDING" and r.data["amount"] == "600.00"
