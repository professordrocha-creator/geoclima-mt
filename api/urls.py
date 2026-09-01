# api/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path("estados/", views.estados_list, name="api_estados"),
    path("municipios/", views.municipios_list, name="api_municipios"),
    path("municipios/<int:municipio_id>/geojson/", views.municipio_geojson, name="api_municipio_geojson"),
    path("municipio-por-ponto/", views.municipio_por_ponto, name="api_municipio_por_ponto"),
    path("municipios/<int:municipio_id>/indicadores/", views.municipio_indicadores, name="api_municipio_indicadores"),
    path("municipios/<int:municipio_id>/spi-serie/", views.municipio_spi_serie, name="api_municipio_spi_serie"),
    path("municipios/<int:municipio_id>/indicadores-fase2/", views.municipio_indicadores_fase2, name="api_municipio_indicadores_fase2"),
    path("municipios/<int:municipio_id>/series-anuais/", views.municipio_series_anuais, name="api_municipio_series_anuais"),
    path("municipios/<int:municipio_id>/exportar/", views.municipio_exportar, name="api_municipio_exportar"),
]
