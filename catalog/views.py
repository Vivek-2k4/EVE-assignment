from django.db import IntegrityError, transaction
from django.db.models import Prefetch, ProtectedError
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from common.exceptions import Conflict
from common.permissions import IsAdminOrReadOnly

from .models import Centre, CentreTest, DiagnosticTest
from .serializers import CentreSerializer, CentreTestSerializer, DiagnosticTestSerializer


class DiagnosticTestViewSet(viewsets.ModelViewSet):
    """Catalogue of test types. Public read, staff write."""

    queryset = DiagnosticTest.objects.all()
    serializer_class = DiagnosticTestSerializer
    permission_classes = [IsAdminOrReadOnly]

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError:
            raise Conflict("This test is offered by a centre and cannot be deleted.")


class CentreViewSet(viewsets.ModelViewSet):
    """Diagnostic centres with the tests (and prices) they offer. Public read, staff write."""

    serializer_class = CentreSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        qs = Centre.objects.prefetch_related(
            Prefetch("centre_tests", queryset=CentreTest.objects.select_related("test").order_by("test__name"))
        )
        params = self.request.query_params
        if location := params.get("location"):
            qs = qs.filter(location__icontains=location)
        if test := params.get("test"):
            if not test.isdigit():
                raise ValidationError({"test": ["Must be a numeric test id."]})
            qs = qs.filter(centre_tests__test_id=int(test))
        return qs.distinct()

    @extend_schema(
        parameters=[
            OpenApiParameter("location", str, description="Case-insensitive location filter"),
            OpenApiParameter("test", int, description="Only centres offering this test id"),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError:
            raise Conflict("This centre has bookings and cannot be deleted.")

    @extend_schema(methods=["POST"], request=CentreTestSerializer, responses=CentreTestSerializer)
    @extend_schema(methods=["GET"], responses=CentreTestSerializer(many=True))
    @action(detail=True, methods=["get", "post"], url_path="tests")
    def tests(self, request, pk=None):
        """GET: tests offered by this centre. POST (staff): offer a test at a price."""
        centre = self.get_object()

        if request.method == "GET":
            qs = centre.centre_tests.select_related("test").order_by("test__name")
            page = self.paginate_queryset(qs)
            return self.get_paginated_response(CentreTestSerializer(page, many=True).data)

        serializer = CentreTestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                centre_test = CentreTest.objects.create(centre=centre, **serializer.validated_data)
        except IntegrityError:
            raise Conflict("This centre already offers this test.")
        return Response(CentreTestSerializer(centre_test).data, status=status.HTTP_201_CREATED)
