from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import IntegrityError, transaction
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from common.exceptions import InvalidCredentials

User = get_user_model()


def tokens_for(user) -> dict:
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="first_name", read_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "full_name"]


class SignupSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    full_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value

    def validate(self, attrs):
        # Run Django's password validators with the user context so
        # "password == email" style choices are rejected.
        candidate = User(username=attrs["email"], email=attrs["email"])
        try:
            validate_password(attrs["password"], user=candidate)
        except Exception as exc:  # DjangoValidationError -> DRF
            raise serializers.ValidationError({"password": list(getattr(exc, "messages", [str(exc)]))})
        return attrs

    def create(self, validated_data):
        try:
            with transaction.atomic():
                return User.objects.create_user(
                    username=validated_data["email"],
                    email=validated_data["email"],
                    password=validated_data["password"],
                    first_name=validated_data.get("full_name", ""),
                )
        except IntegrityError:  # lost a signup race for the same email
            raise serializers.ValidationError({"email": ["A user with this email already exists."]})


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user = authenticate(username=attrs["email"].strip().lower(), password=attrs["password"])
        if user is None or not user.is_active:
            raise InvalidCredentials()
        attrs["user"] = user
        return attrs
