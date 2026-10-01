import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


class InvalidTransition(Exception):
    def __init__(self, current: str, target: str):
        super().__init__(f"Cannot move booking from {current} to {target}.")
        self.current, self.target = current, target


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING"
        CONFIRMED = "CONFIRMED"
        FAILED = "FAILED"
        CANCELLED = "CANCELLED"

    # The single source of truth for the booking lifecycle. FAILED and
    # CANCELLED are terminal, so late/out-of-order payment events can never
    # resurrect or flip a booking.
    ALLOWED_TRANSITIONS = {
        "PENDING": {"CONFIRMED", "FAILED", "CANCELLED"},
        "CONFIRMED": {"CANCELLED"},
        "FAILED": set(),
        "CANCELLED": set(),
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="bookings")
    centre_test = models.ForeignKey("catalog.CentreTest", on_delete=models.PROTECT, related_name="bookings")
    appointment_at = models.DateTimeField()
    # Price snapshot at booking time so later price edits don't rewrite history.
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "-created_at"])]
        constraints = [
            # No double-booking the same test/slot while a booking is still live.
            models.UniqueConstraint(
                fields=["user", "centre_test", "appointment_at"],
                condition=Q(status__in=["PENDING", "CONFIRMED"]),
                name="uniq_active_booking_slot",
            ),
            models.CheckConstraint(condition=Q(amount__gte=0), name="booking_amount_non_negative"),
        ]

    def __str__(self):
        return f"Booking {self.id} [{self.status}]"

    def can_transition_to(self, target) -> bool:
        return str(target) in self.ALLOWED_TRANSITIONS.get(self.status, set())

    def transition_to(self, target) -> None:
        if not self.can_transition_to(target):
            raise InvalidTransition(self.status, str(target))
        self.status = str(target)
        self.save(update_fields=["status", "updated_at"])
