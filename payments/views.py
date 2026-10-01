import json

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from common.exceptions import InvalidSignature

from .serializers import PaymentCreateSerializer, PaymentSerializer, WebhookSerializer
from .services import initiate_payment, process_webhook
from .signature import verify_signature


class PaymentCreateView(APIView):
    @extend_schema(request=PaymentCreateSerializer, responses={201: PaymentSerializer, 200: PaymentSerializer})
    def post(self, request):
        """Simulate paying for a booking. Optional `Idempotency-Key` header makes retries safe."""
        serializer = PaymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        payment, created = initiate_payment(
            user=request.user,
            booking_id=data["booking_id"],
            simulate=data.get("simulate"),
            deferred=data["deferred"],
            idempotency_key=request.headers.get("Idempotency-Key"),
        )
        return Response(
            PaymentSerializer(payment).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PaymentWebhookView(APIView):
    """Receives provider status updates. Authenticated by HMAC signature, not JWT."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(request=WebhookSerializer, responses={200: None}, auth=[])
    def post(self, request):
        raw = request.body  # must be read before request.data; signature covers the exact bytes
        if not verify_signature(raw, request.headers.get("X-Signature")):
            raise InvalidSignature()

        try:
            payload = json.loads(raw)
        except ValueError:
            raise ValidationError({"detail": "Body must be valid JSON."})
        if not isinstance(payload, dict):
            raise ValidationError({"detail": "Body must be a JSON object."})

        serializer = WebhookSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        is_new, outcome = process_webhook(
            event_id=data["event_id"],
            provider_reference=data["provider_reference"],
            status=data["status"],
            payload=payload,
        )
        # 200 for duplicates too: the provider must stop retrying an event we already have.
        return Response({"status": "processed" if is_new else "duplicate", "outcome": outcome})
