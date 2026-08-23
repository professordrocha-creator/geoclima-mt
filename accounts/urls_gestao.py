# accounts/urls_gestao.py
"""
Rotas de gestão de usuários (Etapa 13), separadas de `accounts/urls.py`
(login/registro/senha, público) porque são só pra administrador e
montadas em `/painel/usuarios/` (convenção da área privada), não em
`/accounts/`.
"""
from django.urls import path

from . import views_gestao

app_name = "gestao_usuarios"

urlpatterns = [
    path("", views_gestao.lista_usuarios, name="lista"),
    path("<int:user_id>/bloquear/", views_gestao.alternar_bloqueio, name="alternar_bloqueio"),
    path("<int:user_id>/perfil/", views_gestao.alterar_perfil, name="alterar_perfil"),
]
