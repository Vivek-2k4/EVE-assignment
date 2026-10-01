import pytest

from bookings.models import Booking, InvalidTransition

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "start,target,ok",
    [
        ("PENDING", "CONFIRMED", True),
        ("PENDING", "FAILED", True),
        ("PENDING", "CANCELLED", True),
        ("CONFIRMED", "CANCELLED", True),
        ("CONFIRMED", "FAILED", False),
        ("CONFIRMED", "PENDING", False),
        ("FAILED", "CONFIRMED", False),
        ("FAILED", "CANCELLED", False),
        ("CANCELLED", "CONFIRMED", False),
    ],
)
def test_transition_table(user, make_booking, start, target, ok):
    b = make_booking(user, status=start)
    assert b.can_transition_to(target) is ok
    if ok:
        b.transition_to(target)
        b.refresh_from_db()
        assert b.status == target
    else:
        with pytest.raises(InvalidTransition):
            b.transition_to(target)
        b.refresh_from_db()
        assert b.status == start
