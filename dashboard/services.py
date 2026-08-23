# dashboard/services.py
"""
Agregações de chuva pro dashboard privado (Etapa 8.1) — sempre por
fazenda, somando todas as estações dela (não por estação individual,
que já existe em farms/detalhe_fazenda.html).

Duas fontes, nunca misturadas no mesmo número: dado LOCAL
(RainfallData lançado manualmente/importado, qualquer source_type
exceto 'chirps' — o mais preciso, mas pode não existir) e CHIRPS
(ChirpsData do município da fazenda — só existe pra município
`ativo=True`, mas cobre todo dia desde 1981). "Chuva atual" prioriza
local; "acumulados"/"série" mostram os dois lado a lado, identificados,
pra não fingir que uma estimativa de satélite é uma medição de campo.
"""
from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone

from climate.models import ChirpsData, RainfallData
from climate.validation import pares_chirps_local
from spi.models import SpiResult

JANELAS_ACUMULADO_DIAS = [7, 30, 90]
DIAS_SERIE = 90
ANOS_SERIE_SPI = 10


def _chuva_local_por_dia(farm, desde=None):
    qs = RainfallData.objects.filter(farm=farm).exclude(source_type="chirps")
    if desde:
        qs = qs.filter(date__gte=desde)
    return {
        linha["date"]: linha["total"]
        for linha in qs.values("date").annotate(total=Sum("value")).order_by("date")
    }


def _chuva_chirps_por_dia(farm, desde=None):
    qs = ChirpsData.objects.filter(municipio=farm.municipio)
    if desde:
        qs = qs.filter(date__gte=desde)
    return {registro.date: registro.value for registro in qs.order_by("date")}


def chuva_atual(farm):
    """
    Valor de chuva mais recente disponível: prioriza dado local (mais
    preciso); cai pro CHIRPS do município se ainda não houver
    lançamento local. None se não houver nenhuma das duas fontes
    (município não `ativo=True` e nenhum lançamento local ainda).
    """
    locais = _chuva_local_por_dia(farm)
    if locais:
        data = max(locais)
        return {"date": data, "value": locais[data], "origem": "local"}

    chirps = _chuva_chirps_por_dia(farm)
    if chirps:
        data = max(chirps)
        return {"date": data, "value": chirps[data], "origem": "chirps"}

    return None


def acumulados(farm):
    """Total acumulado (mm) nas últimas janelas (7/30/90 dias), local e CHIRPS lado a lado."""
    hoje = timezone.localdate()
    resultado = []
    for dias in JANELAS_ACUMULADO_DIAS:
        desde = hoje - timedelta(days=dias)
        locais = _chuva_local_por_dia(farm, desde=desde)
        chirps = _chuva_chirps_por_dia(farm, desde=desde)
        resultado.append({
            "dias": dias,
            "local_mm": round(sum(locais.values()), 1) if locais else None,
            "chirps_mm": round(sum(chirps.values()), 1) if chirps else None,
        })
    return resultado


def serie_chuva(farm, dias=DIAS_SERIE):
    """Série diária dos últimos `dias` dias, local e CHIRPS lado a lado (um dos dois pode faltar em cada dia)."""
    hoje = timezone.localdate()
    desde = hoje - timedelta(days=dias)
    locais = _chuva_local_por_dia(farm, desde=desde)
    chirps = _chuva_chirps_por_dia(farm, desde=desde)

    datas = sorted(set(locais) | set(chirps))
    return [
        {"date": data, "local": locais.get(data), "chirps": chirps.get(data)}
        for data in datas
    ]


def serie_spi(farm, anos=ANOS_SERIE_SPI):
    """
    Histórico de SPI-3/6/12 (Etapa 8.2) pra montar um gráfico de
    tendência. O valor do SPI é o mesmo pra todas as estações do
    município num dado (scale, date) — grava-se por estação (Etapa 7.1,
    decisão documentada em DECISOES.md), então pegar TODAS as estações
    da fazenda duplicaria a série; usamos só a primeira estação da
    fazenda como representante.

    Devolve uma linha por DATA (não por escala): `[{"date": ...,
    "spi_3": valor_ou_None, "spi_6": ..., "spi_12": ...}, ...]`, em
    ordem cronológica. Formato "uma linha por data, uma coluna por
    série" de propósito — SPI-12 só começa bem depois de SPI-3 (precisa
    de 12 meses de janela móvel antes do primeiro valor), então as 3
    séries NÃO têm o mesmo tamanho; se cada escala virasse uma lista
    separada, alinhar os 3 datasets do gráfico por índice de array (em
    vez de por data de verdade) desalinharia as datas. Uma linha por
    data, com `None` na escala que ainda não começou, evita esse erro.
    """
    estacao = farm.stations.first()
    if estacao is None:
        return []

    desde = timezone.localdate() - timedelta(days=365 * anos)
    registros = SpiResult.objects.filter(station=estacao, date__gte=desde).order_by("date", "scale")

    por_data = {}
    for registro in registros:
        por_data.setdefault(registro.date, {})[registro.scale] = registro.value

    return [
        {"date": data, "spi_3": valores.get(3), "spi_6": valores.get(6), "spi_12": valores.get(12)}
        for data, valores in sorted(por_data.items())
    ]


def comparacao_chirps_local(farm):
    """
    Pares (CHIRPS, local) por estação já validada da fazenda (Etapa
    8.2) — dado pro gráfico de dispersão que acompanha o cartão de
    métricas da Etapa 7.2 (R²/RMSE/MBE/...) em farms/detalhe_fazenda.html.
    Reaproveita climate.validation.pares_chirps_local, não recalcula
    nada. Estação sem ChirpsValidation ainda (dado local insuficiente)
    não entra na lista.
    """
    resultado = []
    for estacao in farm.stations.all():
        if getattr(estacao, "chirps_validation", None) is None:
            continue
        pares = pares_chirps_local(estacao)
        if pares:
            resultado.append({
                "station": estacao.name,
                "pares": [{"chirps": chirps, "local": local} for chirps, local in pares],
            })
    return resultado
