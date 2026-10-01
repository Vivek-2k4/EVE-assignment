from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from bookings.models import Booking
from catalog.models import Centre, CentreTest, DiagnosticTest

User = get_user_model()
PASSWORD = "S3cure-pass-phrase!"


@pytest.fixture(autouse=True)
def _reset_throttle_cache():
    cache.clear()
    yield


def _client_for(user=None):
    client = APIClient()
    if user is not None:
        client.force_authenticate(user)
    return client


def make_user(email):
    return User.objects.create_user(username=email, email=email, password=PASSWORD)


@pytest.fixture
def user(db):
    return make_user("alice@example.com")


@pytest.fixture
def other_user(db):
    return make_user("bob@example.com")


@pytest.fixture
def staff_user(db):
    u = make_user("admin@example.com")
    u.is_staff = True
    u.save()
    return u


@pytest.fixture
def anon_api():
    return _client_for()


@pytest.fixture
def user_api(user):
    return _client_for(user)


@pytest.fixture
def other_api(other_user):
    return _client_for(other_user)


@pytest.fixture
def staff_api(staff_user):
    return _client_for(staff_user)


@pytest.fixture
def centre_test(db):
    centre = Centre.objects.create(name="EVE Karol Bagh", location="Delhi")
    test = DiagnosticTest.objects.create(name="Lipid Profile")
    return CentreTest.objects.create(centre=centre, test=test, price=Decimal("600.00"))


@pytest.fixture
def future_iso():
    return (timezone.now() + timedelta(days=2)).isoformat()


@pytest.fixture
def make_booking(centre_test):
    def _make(user, days=2, **kwargs):
        return Booking.objects.create(
            user=user,
            centre_test=centre_test,
            appointment_at=timezone.now() + timedelta(days=days),
            amount=centre_test.price,
            **kwargs,
        )

    return _make


@pytest.fixture
def booking(user, make_booking):
    return make_booking(user)
