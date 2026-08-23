# spi/admin.py
from django.contrib import admin

from .models import SpiResult


@admin.register(SpiResult)
class SpiResultAdmin(admin.ModelAdmin):
    list_display = ("date", "scale", "value", "classification", "station", "farm", "owner")
    list_filter = ("scale", "classification")
    search_fields = ("station__name", "farm__name", "owner__username")
    date_hierarchy = "date"
