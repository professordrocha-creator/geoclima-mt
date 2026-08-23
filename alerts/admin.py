# alerts/admin.py
from django.contrib import admin

from .models import Alert


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ("alert_type", "farm", "station", "owner", "is_active", "created_at")
    list_filter = ("alert_type", "is_active")
    search_fields = ("message", "farm__name", "station__name", "owner__username")
    date_hierarchy = "created_at"
