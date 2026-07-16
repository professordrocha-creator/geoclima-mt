# maps/admin.py
from django.contrib import admin
from .models import Municipio


@admin.register(Municipio)
class MunicipioAdmin(admin.ModelAdmin):
    # Lista enxuta (sem geometria) para não pesar a tela do admin.
    list_display = ("nome", "uf", "codigo_ibge", "ativo", "destaque")
    list_filter = ("uf", "ativo", "destaque")
    search_fields = ("nome", "uf", "codigo_ibge")
    ordering = ("uf", "nome")
