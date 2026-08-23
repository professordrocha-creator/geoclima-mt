# climate/quality_checks.py
"""
Detecção de inconsistências no dado local de chuva (Etapa 7.3). Roda
sobre climate.RainfallData (dado lançado manualmente ou importado — não
sobre o CHIRPS, que já vem validado/oficial). Cada função devolve uma
lista de "achados": dicts com station, farm, owner e uma mensagem
começando sempre com "Possível inconsistência detectada" (texto do PDF).

Os 4 itens pedidos no PDF:
- chuva negativa
- valores extremos
- dados duplicados
- falhas temporais
"""
from datetime import timedelta

from .models import RainfallData

# Limiar de "valor extremo" — não é um valor fisicamente impossível (chuvas
# de 200+ mm/dia já foram registradas em eventos raros em MT), é um limiar
# conservador pra sinalizar "revise isso", não pra afirmar que está errado.
LIMITE_VALOR_EXTREMO_MM = 200.0

# Gap mínimo (em dias) entre dois lançamentos consecutivos da mesma estação
# pra considerar "falha temporal" — abaixo disso é só o ritmo normal de
# quem lança manualmente (nem todo mundo lança todo dia).
GAP_MINIMO_FALHA_TEMPORAL_DIAS = 5

# Quantos dias seguidos com o MESMO valor exato pra considerar suspeito
# (sensor travado / erro de cópia).
MINIMO_DIAS_REPETIDOS = 3


def _achado(registro_ou_station, farm, owner, mensagem):
    return {"station": registro_ou_station, "farm": farm, "owner": owner, "message": mensagem}


def detectar_chuva_negativa(queryset=None):
    queryset = queryset if queryset is not None else RainfallData.objects.exclude(source_type="chirps")
    achados = []
    for registro in queryset.filter(value__lt=0).select_related("station", "farm", "owner"):
        achados.append(_achado(
            registro.station, registro.farm, registro.owner,
            f"Possível inconsistência detectada: chuva negativa ({registro.value} mm) "
            f"em {registro.date} na estação {registro.station.name}.",
        ))
    return achados


def detectar_valores_extremos(queryset=None):
    queryset = queryset if queryset is not None else RainfallData.objects.exclude(source_type="chirps")
    achados = []
    for registro in queryset.filter(value__gt=LIMITE_VALOR_EXTREMO_MM).select_related("station", "farm", "owner"):
        achados.append(_achado(
            registro.station, registro.farm, registro.owner,
            f"Possível inconsistência detectada: valor extremo ({registro.value} mm, acima de "
            f"{LIMITE_VALOR_EXTREMO_MM:.0f} mm) em {registro.date} na estação {registro.station.name}.",
        ))
    return achados


def detectar_duplicados(queryset=None):
    """Mesmo valor exato repetido em MINIMO_DIAS_REPETIDOS+ dias consecutivos, por estação."""
    queryset = queryset if queryset is not None else RainfallData.objects.exclude(source_type="chirps")
    achados = []

    estacoes_ids = queryset.values_list("station_id", flat=True).distinct()
    for station_id in estacoes_ids:
        registros = list(
            queryset.filter(station_id=station_id).select_related("station", "farm", "owner").order_by("date")
        )

        sequencia = []
        for registro in registros:
            if sequencia and _sao_consecutivos(sequencia[-1].date, registro.date) and sequencia[-1].value == registro.value:
                sequencia.append(registro)
            else:
                if len(sequencia) >= MINIMO_DIAS_REPETIDOS:
                    achados.append(_gerar_achado_duplicado(sequencia))
                sequencia = [registro]
        if len(sequencia) >= MINIMO_DIAS_REPETIDOS:
            achados.append(_gerar_achado_duplicado(sequencia))

    return achados


def _gerar_achado_duplicado(sequencia):
    primeiro, ultimo = sequencia[0], sequencia[-1]
    return _achado(
        primeiro.station, primeiro.farm, primeiro.owner,
        f"Possível inconsistência detectada: valor {primeiro.value} mm repetido em "
        f"{len(sequencia)} dias seguidos ({primeiro.date} a {ultimo.date}) na estação {primeiro.station.name}.",
    )


def detectar_falhas_temporais(queryset=None):
    """Gap de GAP_MINIMO_FALHA_TEMPORAL_DIAS+ dias entre lançamentos consecutivos de uma estação."""
    queryset = queryset if queryset is not None else RainfallData.objects.exclude(source_type="chirps")
    achados = []

    estacoes_ids = queryset.values_list("station_id", flat=True).distinct()
    for station_id in estacoes_ids:
        registros = list(
            queryset.filter(station_id=station_id).select_related("station", "farm", "owner").order_by("date")
        )
        for anterior, atual in zip(registros, registros[1:]):
            gap = (atual.date - anterior.date).days
            if gap >= GAP_MINIMO_FALHA_TEMPORAL_DIAS:
                achados.append(_achado(
                    atual.station, atual.farm, atual.owner,
                    f"Possível inconsistência detectada: falha temporal de {gap} dias sem lançamento "
                    f"na estação {atual.station.name} (entre {anterior.date} e {atual.date}).",
                ))

    return achados


def _sao_consecutivos(data_anterior, data_atual):
    return (data_atual - data_anterior) == timedelta(days=1)


def rodar_todas_as_checagens(queryset=None):
    """Roda as 4 checagens e devolve uma lista única de achados."""
    return (
        detectar_chuva_negativa(queryset)
        + detectar_valores_extremos(queryset)
        + detectar_duplicados(queryset)
        + detectar_falhas_temporais(queryset)
    )
