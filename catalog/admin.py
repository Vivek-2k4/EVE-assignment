from django.contrib import admin

from .models import Centre, CentreTest, DiagnosticTest


class CentreTestInline(admin.TabularInline):
    model = CentreTest
    extra = 0


@admin.register(Centre)
class CentreAdmin(admin.ModelAdmin):
    list_display = ("name", "location")
    search_fields = ("name", "location")
    inlines = [CentreTestInline]


admin.site.register(DiagnosticTest)
