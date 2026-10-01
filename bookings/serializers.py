from django.utils import timezone
from rest_framework import serializers

from catalog.models import Centre, CentreTest, DiagnosticTest
from catalog.serializers import CentreSummarySerializer, DiagnosticTestSerializer

from .models import Booking


class BookingCreateSerializer(serializers.Serializer):
    centre_id = serializers.PrimaryKeyRelatedField(source="centre", queryset=Centre.objects.all())
    test_id = serializers.PrimaryKeyRelatedField(source="test", queryset=DiagnosticTest.objects.all())
    appointment_at = serializers.DateTimeField()

    def validate_appointment_at(self, value):
        if value <= timezone.now():
            raise serializers.ValidationError("Appointment must be in the future.")
        return value

    def validate(self, attrs):
        try:
            attrs["centre_test"] = CentreTest.objects.get(centre=attrs["centre"], test=attrs["test"])
        except CentreTest.DoesNotExist:
            raise serializers.ValidationError({"test_id": ["This test is not offered at the selected centre."]})
        return attrs


class BookingSerializer(serializers.ModelSerializer):
    centre = CentreSummarySerializer(source="centre_test.centre", read_only=True)
    test = DiagnosticTestSerializer(source="centre_test.test", read_only=True)

    class Meta:
        model = Booking
        fields = ["id", "centre", "test", "appointment_at", "amount", "status", "created_at", "updated_at"]
        read_only_fields = fields
