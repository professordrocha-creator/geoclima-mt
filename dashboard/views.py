# dashboard/views.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from accounts.models import Profile


@login_required
def painel(request):
    """
    Placeholder da área privada (Etapa 4). Só saudação + perfil do
    usuário logado — o dashboard de verdade (chuva, SPI, gráficos,
    comparação CHIRPS x local) é a Etapa 8.

    get_or_create aqui é só uma rede de segurança (o signal em
    accounts/signals.py já cria o Profile no post_save do User); cobre
    o caso raro de um usuário existente antes do signal existir.
    """
    profile, _ = Profile.objects.get_or_create(
        user=request.user, defaults={"profile_type": "produtor"}
    )
    return render(request, "dashboard/painel.html", {"profile": profile})
