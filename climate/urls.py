# climate/urls.py
from django.urls import path

from . import views

app_name = "climate"

urlpatterns = [
    path("", views.lista_lancamentos, name="lista_lancamentos"),
    path("novo/", views.criar_lancamento, name="criar_lancamento"),
    path("<int:lancamento_id>/editar/", views.editar_lancamento, name="editar_lancamento"),
    path("<int:lancamento_id>/excluir/", views.excluir_lancamento, name="excluir_lancamento"),
    path("importar/", views.importar_arquivo, name="importar_arquivo"),
]
