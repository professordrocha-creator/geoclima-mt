# spi/alert_checks.py
"""
Alertas climáticos automáticos derivados do SPI (Etapa 9.1) — diferente
da Etapa 7.3 (climate/quality_checks.py), que detecta problema no DADO
lançado pelo usuário. Isto aqui interpreta o CLIMA em si a partir do
SPI já calculado (Etapa 7.1). Sempre olha só o valor MAIS RECENTE de
cada escala por estação — é sobre a condição climática ATUAL, não um
histórico retrospectivo (rodar `calcular_spi` de novo todo mês e depois
este comando é o fluxo esperado).

Os 4 tipos do PDF, cada um numa combinação diferente de
escala/severidade pra não duplicar o mesmo sinal em dois alertas (ver
docs/DECISOES.md pro raciocínio completo por trás de cada escolha):

- **seca**: SPI-3 (curto prazo, impacto agrícola imediato) em território
  de seca.
- **excesso de chuva**: SPI-3, mesmo motivo, lado úmido.
- **risco hídrico**: SPI-6 (médio prazo — planejamento de irrigação/
  reservatório), só nos dois níveis mais graves de seca.
- **anomalia climática**: SPI-12 (longo prazo), só nos extremos —
  desvio raro e persistente, não uma oscilação normal de estação.
"""
from .models import SpiResult

SECA_CLASSIFICACOES = ("seca_moderada", "seca_severa", "seca_extrema")
EXCESSO_CHUVA_CLASSIFICACOES = ("muito_umido", "extremamente_umido")
RISCO_HIDRICO_CLASSIFICACOES = ("seca_severa", "seca_extrema")
ANOMALIA_CLASSIFICACOES = ("seca_extrema", "extremamente_umido")


def _mais_recente_por_estacao(scale):
    """Um SpiResult por estação: o mais recente daquela escala."""
    mais_recentes = {}
    registros = SpiResult.objects.filter(scale=scale).select_related("station", "farm", "owner").order_by("date")
    for registro in registros:
        mais_recentes[registro.station_id] = registro
    return list(mais_recentes.values())


def _achado(spi_result, alert_type, mensagem):
    return {
        "station": spi_result.station, "farm": spi_result.farm, "owner": spi_result.owner,
        "alert_type": alert_type, "message": mensagem,
    }


def detectar_seca():
    return [
        _achado(
            r, "drought",
            f"Alerta de seca: SPI-3 = {r.value:.2f} ({r.get_classification_display()}) "
            f"em {r.date.strftime('%m/%Y')} na estação {r.station.name}.",
        )
        for r in _mais_recente_por_estacao(3) if r.classification in SECA_CLASSIFICACOES
    ]


def detectar_excesso_chuva():
    return [
        _achado(
            r, "excess_rain",
            f"Alerta de excesso de chuva: SPI-3 = {r.value:.2f} ({r.get_classification_display()}) "
            f"em {r.date.strftime('%m/%Y')} na estação {r.station.name}.",
        )
        for r in _mais_recente_por_estacao(3) if r.classification in EXCESSO_CHUVA_CLASSIFICACOES
    ]


def detectar_risco_hidrico():
    return [
        _achado(
            r, "water_risk",
            f"Risco hídrico: SPI-6 = {r.value:.2f} ({r.get_classification_display()}) "
            f"em {r.date.strftime('%m/%Y')} na estação {r.station.name}.",
        )
        for r in _mais_recente_por_estacao(6) if r.classification in RISCO_HIDRICO_CLASSIFICACOES
    ]


def detectar_anomalia():
    return [
        _achado(
            r, "anomaly",
            f"Anomalia climática: SPI-12 = {r.value:.2f} ({r.get_classification_display()}) "
            f"em {r.date.strftime('%m/%Y')} na estação {r.station.name}.",
        )
        for r in _mais_recente_por_estacao(12) if r.classification in ANOMALIA_CLASSIFICACOES
    ]


def rodar_todas_as_checagens():
    """Roda as 4 checagens e devolve uma lista única de achados."""
    return detectar_seca() + detectar_excesso_chuva() + detectar_risco_hidrico() + detectar_anomalia()
