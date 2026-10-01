from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .models import Booking
from .serializers import BookingCreateSerializer, BookingSerializer
from .services import cancel_booking, create_booking


class BookingViewSet(
    mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """A user's own bookings. Other users' bookings are indistinguishable from non-existent (404)."""

    serializer_class = BookingSerializer

    def get_queryset(self):
        qs = Booking.objects.filter(user=self.request.user).select_related(
            "centre_test__centre", "centre_test__test"
        )
        if status_param := self.request.query_params.get("status"):
            status_param = status_param.upper()
            if status_param not in Booking.Status.values:
                raise ValidationError({"status": [f"Must be one of {', '.join(Booking.Status.values)}."]})
            qs = qs.filter(status=status_param)
        return qs

    @extend_schema(
        parameters=[OpenApiParameter("status", str, enum=Booking.Status.values)],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=BookingCreateSerializer, responses={201: BookingSerializer})
    def create(self, request, *args, **kwargs):
        serializer = BookingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking = create_booking(
            user=request.user,
            centre_test=serializer.validated_data["centre_test"],
            appointment_at=serializer.validated_data["appointment_at"],
        )
        return Response(self.get_serializer(booking).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses={200: BookingSerializer})
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        booking = cancel_booking(user=request.user, booking_id=pk)
        return Response(self.get_serializer(booking).data)
