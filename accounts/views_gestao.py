# accounts/views_gestao.py
"""
Gestão de usuários (Etapa 13) — só administradores acessam. O PDF já
pedia "permissões" dentro de "Cadastro de Usuários" (ver
docs/REQUISITOS.md), mas só o cadastro/login em si foi feito na Etapa
4; gerenciar OUTROS usuários (bloquear, trocar de papel) ficou faltando
até agora, quando o usuário pediu depois de virar administrador.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render

from .models import Profile


def _e_administrador(user):
    """
    Superusuário Django OU profile_type='admin' — os dois contam como
    administrador aqui (o usuário pode ter só um dos dois, dependendo
    de como a conta foi criada; `seed_demo` e a promoção manual desta
    sessão setam ambos, mas não é garantido).
    """
    if not user.is_authenticated:
        return False
    return user.is_superuser or getattr(user, "profile", None) and user.profile.profile_type == "admin"


@login_required
@user_passes_test(_e_administrador, login_url="dashboard:painel")
def lista_usuarios(request):
    usuarios = User.objects.select_related("profile").order_by("username")
    return render(request, "accounts/lista_usuarios.html", {
        "usuarios": usuarios, "perfis": Profile.PROFILE_TYPES,
    })


@login_required
@user_passes_test(_e_administrador, login_url="dashboard:painel")
def alternar_bloqueio(request, user_id):
    if request.method != "POST":
        return redirect("gestao_usuarios:lista")

    usuario = get_object_or_404(User, pk=user_id)
    if usuario == request.user:
        messages.error(request, "Você não pode bloquear a própria conta.")
        return redirect("gestao_usuarios:lista")

    usuario.is_active = not usuario.is_active
    usuario.save()
    acao = "desbloqueado" if usuario.is_active else "bloqueado"
    messages.success(request, f"Usuário \"{usuario.username}\" {acao}.")
    return redirect("gestao_usuarios:lista")


@login_required
@user_passes_test(_e_administrador, login_url="dashboard:painel")
def alterar_perfil(request, user_id):
    if request.method != "POST":
        return redirect("gestao_usuarios:lista")

    usuario = get_object_or_404(User, pk=user_id)
    tipos_validos = dict(Profile.PROFILE_TYPES)
    novo_perfil = request.POST.get("profile_type")

    if novo_perfil not in tipos_validos:
        messages.error(request, "Perfil inválido.")
        return redirect("gestao_usuarios:lista")

    usuario.profile.profile_type = novo_perfil
    usuario.profile.save()
    messages.success(request, f"Perfil de \"{usuario.username}\" alterado para {tipos_validos[novo_perfil]}.")
    return redirect("gestao_usuarios:lista")
