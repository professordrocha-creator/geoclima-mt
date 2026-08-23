# farms/urls.py
from django.urls import path

from . import views

app_name = "farms"

urlpatterns = [
    path("", views.lista_fazendas, name="lista_fazendas"),
    path("nova/", views.criar_fazenda, name="criar_fazenda"),
    path("<int:farm_id>/", views.detalhe_fazenda, name="detalhe_fazenda"),
    path("<int:farm_id>/editar/", views.editar_fazenda, name="editar_fazenda"),
    path("<int:farm_id>/excluir/", views.excluir_fazenda, name="excluir_fazenda"),
    path("<int:farm_id>/talhoes/novo/", views.criar_talhao, name="criar_talhao"),
    path("<int:farm_id>/talhoes/<int:talhao_id>/editar/", views.editar_talhao, name="editar_talhao"),
    path("<int:farm_id>/talhoes/<int:talhao_id>/excluir/", views.excluir_talhao, name="excluir_talhao"),
    path("<int:farm_id>/poligono.json", views.poligono_fazenda_json, name="poligono_fazenda_json"),
    path("<int:farm_id>/relatorio/", views.relatorio_fazenda, name="relatorio_fazenda"),
    path("<int:farm_id>/exportar.xlsx", views.exportar_fazenda_excel, name="exportar_fazenda_excel"),
]
