# stations/admin.py
from django.contrib import admin

from .models import Station


@admin.register(Station)
class StationAdmin(admin.ModelAdmin):
    list_display = ("name", "station_type", "farm", "owner")
    list_filter = ("station_type",)
    search_fields = ("name", "farm__name", "owner__username")
    autocomplete_fields = ("farm",)
