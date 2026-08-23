# farms/admin.py
from django.contrib import admin

from .models import Farm, Talhao


class TalhaoInline(admin.TabularInline):
    model = Talhao
    extra = 0


@admin.register(Farm)
class FarmAdmin(admin.ModelAdmin):
    list_display = ("name", "municipio", "owner", "area", "crop")
    list_filter = ("municipio__uf",)
    search_fields = ("name", "owner__username", "municipio__nome")
    autocomplete_fields = ("municipio",)
    inlines = (TalhaoInline,)


@admin.register(Talhao)
class TalhaoAdmin(admin.ModelAdmin):
    list_display = ("name", "farm", "owner", "area", "crop")
    search_fields = ("name", "farm__name", "owner__username")
