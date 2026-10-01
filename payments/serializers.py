from django.conf import settings
from rest_framework import serializers

from .models import Payment


class PaymentCreateSerializer(serializers.Serializer):
    booking_id = serializers.UUIDField()
    simulate = serializers.ChoiceField(
        choices=[Payment.Status.SUCCESS, Payment.Status.FAILED],
        required=False,
        help_text="Force the simulated outcome (useful for tests/demos).",
    )
    deferred = serializers.BooleanField(
        default=False, help_text="Leave the payment PENDING; the webhook will settle it."
    )

    def validate(self, attrs):
        if attrs.get("simulate") and attrs.get("deferred"):
            raise serializers.ValidationError("'simulate' cannot be combined with 'deferred'.")
        if attrs.get("simulate") and not settings.PAYMENT_ALLOW_SIMULATE:
            raise serializers.ValidationError({"simulate": ["Not allowed in this environment."]})
        return attrs


class PaymentSerializer(serializers.ModelSerializer):
    booking_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Payment
        fields = ["id", "booking_id", "amount", "status", "provider_reference", "created_at"]
        read_only_fields = fields


class WebhookSerializer(serializers.Serializer):
    event_id = serializers.CharField(max_length=128)
    provider_reference = serializers.CharField(max_length=64)
    status = serializers.ChoiceField(choices=[Payment.Status.SUCCESS, Payment.Status.FAILED])
