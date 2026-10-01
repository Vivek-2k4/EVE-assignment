import pytest

from catalog.models import Centre, CentreTest, DiagnosticTest

pytestmark = pytest.mark.django_db


def test_public_can_list_centres_with_tests_and_prices(anon_api, centre_test):
    r = anon_api.get("/centres/")
    assert r.status_code == 200
    centre = r.data["results"][0]
    assert centre["name"] == "EVE Karol Bagh"
    assert centre["tests"][0]["test"]["name"] == "Lipid Profile"
    assert centre["tests"][0]["price"] == "600.00"


def test_filter_centres_by_location_and_test(anon_api, centre_test):
    Centre.objects.create(name="Other", location="Pune")
    assert len(anon_api.get("/centres/?location=delhi").data["results"]) == 1
    assert len(anon_api.get(f"/centres/?test={centre_test.test_id}").data["results"]) == 1
    assert anon_api.get("/centres/?test=abc").status_code == 400


def test_centre_tests_endpoint(anon_api, centre_test):
    r = anon_api.get(f"/centres/{centre_test.centre_id}/tests/")
    assert r.status_code == 200 and r.data["count"] == 1
    assert anon_api.get("/centres/9999/tests/").status_code == 404


def test_non_staff_cannot_write(user_api, anon_api):
    body = {"name": "X", "location": "Y"}
    assert anon_api.post("/centres/", body, format="json").status_code == 401
    assert user_api.post("/centres/", body, format="json").status_code == 403


def test_staff_can_create_centre_test_and_attach_with_price(staff_api):
    c = staff_api.post("/centres/", {"name": "New Centre", "location": "Mumbai"}, format="json")
    assert c.status_code == 201
    t = staff_api.post("/tests/", {"name": "HbA1c"}, format="json")
    assert t.status_code == 201
    r = staff_api.post(f"/centres/{c.data['id']}/tests/", {"test_id": t.data["id"], "price": "450.00"}, format="json")
    assert r.status_code == 201 and r.data["price"] == "450.00"


def test_attach_same_test_twice_conflicts(staff_api, centre_test):
    r = staff_api.post(
        f"/centres/{centre_test.centre_id}/tests/", {"test_id": centre_test.test_id, "price": "1.00"}, format="json"
    )
    assert r.status_code == 409


@pytest.mark.parametrize("price", ["0", "-5", "abc"])
def test_invalid_price_rejected(staff_api, centre_test, price):
    t = DiagnosticTest.objects.create(name="Other test")
    r = staff_api.post(f"/centres/{centre_test.centre_id}/tests/", {"test_id": t.id, "price": price}, format="json")
    assert r.status_code == 400


def test_duplicate_centre_rejected(staff_api, centre_test):
    r = staff_api.post("/centres/", {"name": "eve karol bagh", "location": "DELHI"}, format="json")
    assert r.status_code == 400


def test_cannot_delete_centre_with_bookings(staff_api, booking):
    r = staff_api.delete(f"/centres/{booking.centre_test.centre_id}/")
    assert r.status_code == 409
    assert Centre.objects.count() == 1 and CentreTest.objects.count() == 1
