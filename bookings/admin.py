from django.contrib import admin

from .models import Booking


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "centre_test", "appointment_at", "amount", "status")
    list_filter = ("status",)
