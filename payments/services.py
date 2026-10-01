import logging
import random

from django.conf import settings
from django.db import transaction
from rest_framework.exceptions import NotFound

from bookings.models import Booking
from common.exceptions import Conflict

from .models import Payment, WebhookEvent

logger = logging.getLogger(__name__)


def initiate_payment(*, user, booking_id, simulate=None, deferred=False, idempotency_key=None):
    """Simulate a payment for one of the user's PENDING bookings.

    Returns (payment, created). `created` is False when an Idempotency-Key replay
    returns the payment from the original request.

    deferred=True leaves the payment PENDING, to be settled later by the webhook.
    """
    with transaction.atomic():
        # Lock the booking row: concurrent pay/cancel/webhook calls queue up here.
        booking = Booking.objects.select_for_update().filter(pk=booking_id, user=user).first()
        if booking is None:
            raise NotFound("Booking not found.")

        existing = Payment.objects.filter(booking=booking).first()
        if existing:
            if idempotency_key and existing.idempotency_key == idempotency_key:
                return existing, False
            raise Conflict("A payment already exists for this booking.")

        if booking.status != Booking.Status.PENDING:
            raise Conflict(f"Booking is {booking.status}; only PENDING bookings can be paid.")

        payment = Payment(booking=booking, amount=booking.amount, idempotency_key=idempotency_key)
        if deferred:
            payment.status = Payment.Status.PENDING
        else:
            outcome = simulate or (
                Payment.Status.SUCCESS if random.random() < settings.PAYMENT_SUCCESS_RATE else Payment.Status.FAILED
            )
            payment.status = outcome
            booking.transition_to(
                Booking.Status.CONFIRMED if outcome == Payment.Status.SUCCESS else Booking.Status.FAILED
            )
        payment.save()

    logger.info(
        "payment_processed",
        extra={"ctx": {"payment_id": payment.id, "booking_id": booking.id, "status": payment.status}},
    )
    return payment, True


def process_webhook(*, event_id, provider_reference, status, payload):
    """Apply a provider status update exactly once.

    Returns (is_new, outcome). The WebhookEvent row, the payment update and the
    booking transition commit atomically. If anything raises (e.g. unknown
    payment), the event row rolls back too, so a provider retry is processed
    normally. A replay of an already-committed event_id is a no-op.
    """
    with transaction.atomic():
        event, created = WebhookEvent.objects.get_or_create(
            event_id=event_id, defaults={"payload": payload, "outcome": "processing"}
        )
        if not created:
            logger.info("webhook_duplicate", extra={"ctx": {"event_id": event_id}})
            return False, event.outcome

        payment = Payment.objects.select_for_update().filter(provider_reference=provider_reference).first()
        if payment is None:
            raise NotFound("Unknown payment reference.")
        booking = Booking.objects.select_for_update().get(pk=payment.booking_id)

        if payment.status == status:
            outcome = "noop_already_in_state"
        elif payment.status == Payment.Status.PENDING:
            payment.status = status
            payment.save(update_fields=["status", "updated_at"])
            target = Booking.Status.CONFIRMED if status == Payment.Status.SUCCESS else Booking.Status.FAILED
            if booking.can_transition_to(target):
                booking.transition_to(target)
                outcome = "applied"
            else:
                # e.g. user cancelled while payment was in flight; needs refund handling.
                outcome = "payment_updated_booking_unchanged"
                logger.warning(
                    "webhook_booking_not_updated",
                    extra={"ctx": {"booking_id": booking.id, "booking_status": booking.status, "payment_status": status}},
                )
        else:
            # Payment already settled differently: terminal states are not overwritten.
            outcome = "ignored_conflict"
            logger.warning(
                "webhook_conflict_ignored",
                extra={"ctx": {"payment_id": payment.id, "current": payment.status, "received": status}},
            )

        event.payment, event.outcome = payment, outcome
        event.save(update_fields=["payment", "outcome"])

    logger.info("webhook_processed", extra={"ctx": {"event_id": event_id, "outcome": outcome}})
    return True, outcome
