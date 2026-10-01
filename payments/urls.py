from django.urls import path

from .views import PaymentCreateView, PaymentWebhookView

urlpatterns = [
    path("", PaymentCreateView.as_view(), name="payment-create"),
    path("webhook/", PaymentWebhookView.as_view(), name="payment-webhook"),
]
