# dashboard/insights.py
"""
Insights de texto pro dashboard privado (Etapa 9.2) — interpretação em
REGRAS simples do SPI já calculado (Etapa 7.1) e dos alertas
climáticos já gerados (Etapa 9.1), SEM IA/ML (decisão confirmada com o
usuário). Cobre os itens do PDF ("Insights para Tomada de Decisão"):
risco de déficit hídrico, tendência de seca, janela de plantio, risco
climático, necessidade de irrigação, tendência pluviométrica, apoio à
gestão hídrica.

Vários desses itens são reformulações do MESMO sinal de curto prazo
(déficit hídrico, necessidade de irrigação e janela de plantio são
lidos do mesmo SPI-3) — de propósito, pra não gerar 3 frases repetindo
a mesma leitura com palavras diferentes. Reaproveita
`spi.services.classificar_spi` (não duplica os limiares) e os
`alerts.Alert` já gerados pela 9.1 (não recalcula nada).

O sistema DESCREVE o estado climático indicado pelo SPI — não
RECOMENDA ação (não decide se é hora de irrigar, plantar, etc.). Isso
é revisão explícita: uma versão anterior tinha frases prescritivas
("pode ser hora de considerar irrigação") que confundiam a leitura
estatística do SPI com uma recomendação agronômica, que este sistema
não tem base pra fazer.
"""
from spi.services import classificar_spi

CLASSIFICACOES_SECAS = {"seca_moderada", "seca_severa", "seca_extrema"}
# Inclui moderadamente_umido (Correção 1 — LIMIARES_CLASSIFICACAO em
# spi/services.py ganhou essa faixa, que faltava na tabela de McKee).
CLASSIFICACOES_UMIDAS = {"moderadamente_umido", "muito_umido", "extremamente_umido"}

# limiar empírico adotado neste sistema — sem referência publicada.
LIMIAR_TENDENCIA = 0.3
# Magnitude de queda do SPI-3 considerada atípica quando ocorre FORA do
# período seco (out-mar, estação chuvosa em MT) — ver _insight_tendencia.
LIMIAR_QUEDA_ATIPICA = 0.5
# abr-set: transição chuvoso->seco esperada em Mato Grosso todo ano;
# uma queda do SPI-3 nesse intervalo é sazonalmente normal, não um sinal
# de alerta. Ver docs/DECISOES.md.
MESES_PERIODO_SECO_MT = {4, 5, 6, 7, 8, 9}


def gerar_insights(dados_spi, alertas_climaticos):
    """
    dados_spi: saída de dashboard.services.serie_spi(farm) (lista, uma
    linha por data, colunas spi_3/spi_6/spi_12). alertas_climaticos:
    queryset/lista de Alert já filtrada (farm, tipos climáticos,
    is_active) — passada de fora, não reconsultada aqui.
    """
    linhas_spi3 = [linha for linha in dados_spi if linha["spi_3"] is not None]
    if not linhas_spi3:
        return [{
            "icone": "fa-circle-info",
            "texto": (
                "Ainda não há SPI suficiente pra esta fazenda pra gerar insights "
                "(precisa de CHIRPS habilitado pro município e histórico mínimo)."
            ),
        }]

    insights = [_insight_curto_prazo(linhas_spi3[-1]["spi_3"])]

    if len(linhas_spi3) >= 3:
        insights.append(_insight_tendencia(linhas_spi3[-3:]))

    linhas_spi6 = [linha for linha in dados_spi if linha["spi_6"] is not None]
    if linhas_spi6:
        insight_gestao = _insight_gestao_hidrica(linhas_spi6[-1]["spi_6"])
        if insight_gestao:
            insights.append(insight_gestao)

    if alertas_climaticos:
        insights.append(_insight_risco_climatico(alertas_climaticos))

    return insights


def _insight_curto_prazo(spi3_atual):
    """
    Déficit hídrico / necessidade de irrigação / janela de plantio —
    mesmo sinal de curto prazo (SPI-3), descrito como anomalia de
    PRECIPITAÇÃO (o que o SPI mede) — não como "umidade do solo"
    (o SPI não mede isso) nem como recomendação de manejo.
    """
    classificacao = classificar_spi(spi3_atual)
    if classificacao in CLASSIFICACOES_SECAS:
        return {
            "icone": "fa-droplet-slash",
            "texto": (
                "Precipitação acumulada abaixo da média histórica — anomalia negativa "
                f"de curto prazo (SPI-3 = {spi3_atual:.2f})."
            ),
        }
    if classificacao in CLASSIFICACOES_UMIDAS:
        return {
            "icone": "fa-droplet",
            "texto": (
                "Precipitação acumulada acima da média histórica — anomalia positiva "
                f"de curto prazo (SPI-3 = {spi3_atual:.2f})."
            ),
        }
    return {
        "icone": "fa-circle-check",
        "texto": (
            f"Precipitação acumulada dentro da faixa esperada para o período "
            f"(SPI-3 = {spi3_atual:.2f})."
        ),
    }


def _insight_tendencia(ultimas_tres_linhas):
    """
    Tendência de seca / tendência pluviométrica — variação do SPI-3 nos
    últimos 3 meses disponíveis, com contexto sazonal: MT tem uma
    transição chuvoso->seco previsível todo ano (abr-set) — uma queda
    do SPI-3 inteiramente dentro desse intervalo é esperada, não é
    alerta. Fora dele (out-mar, estação chuvosa), a mesma queda é
    incomum e vale destacar com mais ênfase se for grande o bastante
    (>= LIMIAR_QUEDA_ATIPICA). Melhora e estável não mudam de
    comportamento com o mês — só a leitura de piora ganha esse
    contexto.
    """
    valores = [linha["spi_3"] for linha in ultimas_tres_linhas]
    meses = [linha["date"].month for linha in ultimas_tres_linhas]
    variacao = valores[-1] - valores[0]

    if variacao <= -LIMIAR_TENDENCIA:
        dentro_periodo_seco = all(mes in MESES_PERIODO_SECO_MT for mes in meses)
        if dentro_periodo_seco:
            return {
                "icone": "fa-arrow-trend-down",
                "texto": (
                    f"SPI-3 caiu de {valores[0]:.2f} pra {valores[-1]:.2f}, consistente "
                    "com a transição sazonal (período seco) — comportamento esperado "
                    "pra a época."
                ),
            }
        if variacao <= -LIMIAR_QUEDA_ATIPICA:
            return {
                "icone": "fa-triangle-exclamation",
                "texto": (
                    f"SPI-3 caiu de {valores[0]:.2f} pra {valores[-1]:.2f} durante o "
                    "período chuvoso — tendência atípica que merece acompanhamento."
                ),
            }
        return {
            "icone": "fa-arrow-trend-down",
            "texto": (
                f"Tendência de piora: o SPI-3 caiu de {valores[0]:.2f} pra "
                f"{valores[-1]:.2f} nos últimos 3 meses — condição ficando mais seca."
            ),
        }
    if variacao >= LIMIAR_TENDENCIA:
        return {
            "icone": "fa-arrow-trend-up",
            "texto": (
                f"Tendência de melhora: o SPI-3 subiu de {valores[0]:.2f} pra "
                f"{valores[-1]:.2f} nos últimos 3 meses — condição ficando mais úmida."
            ),
        }
    return {
        "icone": "fa-minus",
        "texto": "Tendência estável nos últimos 3 meses (SPI-3 sem variação relevante).",
    }


def _insight_gestao_hidrica(spi6_atual):
    """Apoio à gestão hídrica — só fala algo quando há déficit de médio prazo (SPI-6) que mereça atenção."""
    if classificar_spi(spi6_atual) in CLASSIFICACOES_SECAS:
        return {
            "icone": "fa-water",
            "texto": (
                "Precipitação acumulada abaixo da média histórica em janela de médio "
                f"prazo (SPI-6 = {spi6_atual:.2f})."
            ),
        }
    return None


def _insight_risco_climatico(alertas_climaticos):
    """Risco climático — reaproveita os alertas já gerados na Etapa 9.1, não recalcula nada."""
    quantidade = len(alertas_climaticos)
    plural = "s" if quantidade != 1 else ""
    return {
        "icone": "fa-triangle-exclamation",
        "texto": (
            f"Risco climático: {quantidade} alerta{plural} climático{plural} ativo{plural} "
            "pra esta fazenda — ver detalhes na página da fazenda."
        ),
    }
