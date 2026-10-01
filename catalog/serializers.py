from rest_framework import serializers

from .models import Centre, CentreTest, DiagnosticTest


class DiagnosticTestSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiagnosticTest
        fields = ["id", "name", "description"]


class CentreTestSerializer(serializers.ModelSerializer):
    """Read: nested test + price. Write: {"test_id": 1, "price": "499.00"}."""

    test = DiagnosticTestSerializer(read_only=True)
    test_id = serializers.PrimaryKeyRelatedField(
        source="test", queryset=DiagnosticTest.objects.all(), write_only=True
    )

    class Meta:
        model = CentreTest
        fields = ["id", "test", "test_id", "price"]


class CentreSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Centre
        fields = ["id", "name", "location"]


class CentreSerializer(serializers.ModelSerializer):
    tests = CentreTestSerializer(source="centre_tests", many=True, read_only=True)

    class Meta:
        model = Centre
        fields = ["id", "name", "location", "tests"]

    def validate(self, attrs):
        name = attrs.get("name", getattr(self.instance, "name", None))
        location = attrs.get("location", getattr(self.instance, "location", None))
        clash = Centre.objects.filter(name__iexact=name, location__iexact=location)
        if self.instance:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("A centre with this name and location already exists.")
        return attrs
