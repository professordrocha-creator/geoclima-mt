# dashboard/views.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render

from accounts.models import Profile
from alerts.models import Alert
from farms.models import Farm
from .insights import gerar_insights
from .services import acumulados, chuva_atual, comparacao_chirps_local, serie_chuva, serie_spi

TIPOS_ALERTA_CLIMATICO = ["drought", "excess_rain", "water_risk", "anomaly"]


@login_required
def painel(request):
    """
    Área privada (Etapa 4 placeholder, Etapa 8.1 em diante ganha dado de
    verdade). Sem fazenda cadastrada, mostra só a saudação de sempre. Com
    fazenda, mostra um seletor (a mesma view estendida, sem rota nova —
    ver docs/DECISOES.md sobre isso) e as agregações de chuva da fazenda
    escolhida (query param ?fazenda=<id>, padrão a primeira do usuário).
    """
    profile, _ = Profile.objects.get_or_create(
        user=request.user, defaults={"profile_type": "produtor"}
    )

    fazendas = Farm.objects.filter(owner=request.user).order_by("name")
    fazenda_selecionada = None
    dados_chuva = None
    dados_spi = None
    spi_disponivel = False
    dados_comparacao = None
    insights = None

    if fazendas.exists():
        fazenda_id = request.GET.get("fazenda")
        if fazenda_id:
            fazenda_selecionada = get_object_or_404(fazendas, pk=fazenda_id)
        else:
            fazenda_selecionada = fazendas.first()

        dados_chuva = {
            "atual": chuva_atual(fazenda_selecionada),
            "acumulados": acumulados(fazenda_selecionada),
            "serie": serie_chuva(fazenda_selecionada),
        }
        dados_spi = serie_spi(fazenda_selecionada)
        spi_disponivel = bool(dados_spi)
        dados_comparacao = comparacao_chirps_local(fazenda_selecionada)

        alertas_climaticos = Alert.objects.filter(
            farm=fazenda_selecionada, alert_type__in=TIPOS_ALERTA_CLIMATICO, is_active=True,
        )
        insights = gerar_insights(dados_spi, alertas_climaticos)

    return render(request, "dashboard/painel.html", {
        "profile": profile,
        "fazendas": fazendas,
        "fazenda_selecionada": fazenda_selecionada,
        "dados_chuva": dados_chuva,
        "dados_spi": dados_spi,
        "spi_disponivel": spi_disponivel,
        "dados_comparacao": dados_comparacao,
        "insights": insights,
    })
