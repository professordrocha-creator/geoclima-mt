# api/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("estados/", views.estados_list, name="api_estados"),
    path("municipios/", views.municipios_list, name="api_municipios"),
    path("municipios/<int:municipio_id>/geojson/", views.municipio_geojson, name="api_municipio_geojson"),
]
