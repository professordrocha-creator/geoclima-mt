# climate/admin.py
from django.contrib import admin

from .models import ChirpsData, ChirpsValidation, Projection, RainfallData


@admin.register(RainfallData)
class RainfallDataAdmin(admin.ModelAdmin):
    list_display = ("date", "value", "source_type", "station", "farm", "owner")
    list_filter = ("source_type",)
    search_fields = ("station__name", "farm__name", "owner__username")
    date_hierarchy = "date"


@admin.register(ChirpsData)
class ChirpsDataAdmin(admin.ModelAdmin):
    list_display = ("date", "value", "municipio")
    list_filter = ("municipio__uf",)
    search_fields = ("municipio__nome",)
    date_hierarchy = "date"


@admin.register(ChirpsValidation)
class ChirpsValidationAdmin(admin.ModelAdmin):
    list_display = ("station", "n_pares", "r2", "rmse", "mbe", "indice_c", "desempenho_c", "calculado_em")
    list_filter = ("desempenho_c",)
    search_fields = ("station__name", "farm__name", "owner__username")


@admin.register(Projection)
class ProjectionAdmin(admin.ModelAdmin):
    list_display = ("date", "scenario", "value", "owner")
    search_fields = ("scenario", "owner__username")
