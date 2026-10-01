import uuid

from django.db import models


def _provider_reference() -> str:
    return f"sim_{uuid.uuid4().hex[:24]}"


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING"
        SUCCESS = "SUCCESS"
        FAILED = "FAILED"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # OneToOne: a booking is paid for at most once. A FAILED payment means a
    # FAILED booking, so retrying means creating a new booking.
    booking = models.OneToOneField("bookings.Booking", on_delete=models.PROTECT, related_name="payment")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    # Identifier the (simulated) provider uses; webhooks refer to payments by it.
    provider_reference = models.CharField(max_length=64, unique=True, default=_provider_reference, editable=False)
    # Client-supplied Idempotency-Key for POST /payments/ replays.
    idempotency_key = models.CharField(max_length=128, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Payment {self.provider_reference} [{self.status}]"


class WebhookEvent(models.Model):
    """Ledger of processed webhook events. The unique event_id is the idempotency guard."""

    event_id = models.CharField(max_length=128, unique=True)
    payment = models.ForeignKey(Payment, null=True, on_delete=models.SET_NULL, related_name="webhook_events")
    payload = models.JSONField()
    outcome = models.CharField(max_length=64)
    received_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.event_id} -> {self.outcome}"
