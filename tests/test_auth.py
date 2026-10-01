import pytest

from tests.conftest import PASSWORD, make_user

pytestmark = pytest.mark.django_db


def test_signup_returns_user_and_tokens(anon_api):
    r = anon_api.post("/auth/signup/", {"email": "New@Example.com", "password": PASSWORD, "full_name": "New User"}, format="json")
    assert r.status_code == 201
    assert r.data["user"]["email"] == "new@example.com"
    assert r.data["access"] and r.data["refresh"]
    assert "password" not in r.data["user"]


def test_signup_duplicate_email_case_insensitive(anon_api, user):
    r = anon_api.post("/auth/signup/", {"email": "ALICE@example.com", "password": PASSWORD}, format="json")
    assert r.status_code == 400
    assert r.data["error"]["code"] == "validation_error"
    assert "email" in r.data["error"]["details"]


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email", "password": PASSWORD},
        {"email": "a@example.com", "password": "123"},
        {"email": "a@example.com", "password": "password"},
        {"email": "a@example.com"},
        {},
    ],
)
def test_signup_validation(anon_api, payload):
    r = anon_api.post("/auth/signup/", payload, format="json")
    assert r.status_code == 400
    assert r.data["error"]["code"] == "validation_error"


def test_login_and_use_jwt_on_protected_endpoint(anon_api, user):
    r = anon_api.post("/auth/login/", {"email": "alice@example.com", "password": PASSWORD}, format="json")
    assert r.status_code == 200
    anon_api.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
    assert anon_api.get("/bookings/").status_code == 200


def test_login_wrong_password(anon_api, user):
    r = anon_api.post("/auth/login/", {"email": "alice@example.com", "password": "wrong-password-1"}, format="json")
    assert r.status_code == 401
    assert r.data["error"]["code"] == "invalid_credentials"


def test_login_unknown_user_gives_same_error(anon_api):
    r = anon_api.post("/auth/login/", {"email": "ghost@example.com", "password": PASSWORD}, format="json")
    assert r.status_code == 401
    assert r.data["error"]["code"] == "invalid_credentials"


def test_protected_endpoint_requires_token(anon_api):
    assert anon_api.get("/bookings/").status_code == 401
    assert anon_api.post("/payments/", {}, format="json").status_code == 401


def test_garbage_token_rejected(anon_api):
    anon_api.credentials(HTTP_AUTHORIZATION="Bearer not.a.jwt")
    assert anon_api.get("/bookings/").status_code == 401


def test_refresh_token_flow(anon_api, user):
    login = anon_api.post("/auth/login/", {"email": "alice@example.com", "password": PASSWORD}, format="json")
    r = anon_api.post("/auth/refresh/", {"refresh": login.data["refresh"]}, format="json")
    assert r.status_code == 200 and r.data["access"]
