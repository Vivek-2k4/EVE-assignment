from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q


class Centre(models.Model):
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=255, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["name", "location"], name="uniq_centre_name_location")
        ]

    def __str__(self):
        return f"{self.name} ({self.location})"


class DiagnosticTest(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class CentreTest(models.Model):
    """A test offered by a centre. Price lives here because it differs per centre."""

    centre = models.ForeignKey(Centre, on_delete=models.CASCADE, related_name="centre_tests")
    test = models.ForeignKey(DiagnosticTest, on_delete=models.PROTECT, related_name="centre_tests")
    price = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["centre", "test"], name="uniq_centre_test"),
            models.CheckConstraint(condition=Q(price__gt=0), name="centretest_price_positive"),
        ]

    def __str__(self):
        return f"{self.test} @ {self.centre} - {self.price}"
