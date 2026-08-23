# stations/urls.py
from django.urls import path

from . import views

app_name = "stations"

urlpatterns = [
    path("", views.lista_estacoes, name="lista_estacoes"),
    path("nova/", views.criar_estacao, name="criar_estacao"),
    path("<int:station_id>/editar/", views.editar_estacao, name="editar_estacao"),
    path("<int:station_id>/excluir/", views.excluir_estacao, name="excluir_estacao"),
]
