import logging

from django.db import IntegrityError, transaction
from rest_framework.exceptions import NotFound

from common.exceptions import Conflict

from .models import Booking, InvalidTransition

logger = logging.getLogger(__name__)


def create_booking(*, user, centre_test, appointment_at) -> Booking:
    try:
        with transaction.atomic():
            booking = Booking.objects.create(
                user=user,
                centre_test=centre_test,
                appointment_at=appointment_at,
                amount=centre_test.price,
            )
    except IntegrityError:
        # uniq_active_booking_slot: same user, test and slot already live.
        raise Conflict("You already have an active booking for this test at this time.")
    logger.info("booking_created", extra={"ctx": {"booking_id": booking.id, "user_id": user.id}})
    return booking


def cancel_booking(*, user, booking_id) -> Booking:
    with transaction.atomic():
        # Row lock serialises cancel vs. a concurrent payment/webhook on the same booking.
        booking = Booking.objects.select_for_update().filter(pk=booking_id, user=user).first()
        if booking is None:
            raise NotFound("Booking not found.")
        try:
            booking.transition_to(Booking.Status.CANCELLED)
        except InvalidTransition:
            raise Conflict(f"A booking that is {booking.status} cannot be cancelled.")
    logger.info("booking_cancelled", extra={"ctx": {"booking_id": booking.id}})
    return booking
