from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .serializers import LoginSerializer, SignupSerializer, UserSerializer, tokens_for


class _AuthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class SignupView(_AuthView):
    @extend_schema(request=SignupSerializer, responses={201: None}, auth=[])
    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        body = {"user": UserSerializer(user).data, **tokens_for(user)}
        return Response(body, status=status.HTTP_201_CREATED)


class LoginView(_AuthView):
    @extend_schema(request=LoginSerializer, responses={200: None}, auth=[])
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        return Response({"user": UserSerializer(user).data, **tokens_for(user)})
