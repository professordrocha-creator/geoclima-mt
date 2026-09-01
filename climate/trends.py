# climate/trends.py
"""
Análise histórica, tendência temporal e cenários futuros do CHIRPS
(Etapa 10) — SEM machine learning (o PDF marca "machine learning; IA
climática; modelos preditivos" explicitamente como "Futuro", fora do
escopo desta etapa; decisão de interpretação confirmada com o usuário
antes de codar).

Duas ideias, as duas usando só estatística descritiva simples:

1. **Tendência**: regressão linear simples (totais anuais → ano), com
   `statistics.linear_regression` nativo do Python 3.10+ — mesma
   família de `statistics.correlation` já usada em
   `climate/validation.py` (Etapa 7.2), sem dependência nova.
2. **Normais climatológicas / cenários futuros**: estatística (média,
   mediana, percentis) dos totais mensais agrupados por MÊS DO
   CALENDÁRIO em todos os anos históricos — mesma técnica de
   agrupamento já usada em `spi/services.py` (Etapa 7.1) pro SPI, só
   que aqui vira "o que normalmente chove nesse mês, historicamente"
   em vez de um z-score. Um "cenário futuro" aqui é uma FAIXA
   estatística (seco/normal/úmido = percentis 25/50/75 do histórico),
   não uma previsão de modelo climático.
"""
import statistics
from collections import defaultdict

from django.db.models import Sum
from django.db.models.functions import TruncMonth, TruncYear
from django.utils import timezone

from .models import ChirpsData

MINIMO_ANOS_TENDENCIA = 10  # mesma janela mínima já usada no SPI (Etapa 7.1)
MINIMO_ANOS_NORMAL_CLIMATOLOGICA = 5
MESES_CENARIO_FUTURO = 6


def totais_anuais(municipio):
    """
    dict {ano: total_mm}, só com anos CIVIS COMPLETOS — exclui o ano
    corrente (sempre parcial), mesmo critério já usado no resumo do
    backfill histórico (Etapa 3.2, ver HISTORICO.md).
    """
    ano_atual = timezone.localdate().year
    linhas = (
        ChirpsData.objects.filter(municipio=municipio)
        .exclude(date__year=ano_atual)
        .annotate(ano=TruncYear("date"))
        .values("ano")
        .annotate(total=Sum("value"))
        .order_by("ano")
    )
    return {linha["ano"].year: linha["total"] for linha in linhas}


def tendencia_anual(municipio):
    """
    Regressão linear simples (ano → total anual em mm) — tendência de
    longo prazo. None se não houver pelo menos MINIMO_ANOS_TENDENCIA
    anos civis completos (não dá pra falar de tendência com poucos
    anos de amostra).
    """
    totais = totais_anuais(municipio)
    if len(totais) < MINIMO_ANOS_TENDENCIA:
        return None

    anos = sorted(totais)
    valores = [totais[ano] for ano in anos]
    slope, intercepto = statistics.linear_regression(anos, valores)

    return {
        "anos": anos,
        "valores": valores,
        "slope_mm_por_ano": slope,
        "intercepto": intercepto,
        "primeiro_ano": anos[0],
        "ultimo_ano": anos[-1],
        "n_anos": len(anos),
    }


def totais_mensais(municipio):
    """
    dict {date(primeiro dia do mês): total_mm} — um total por MÊS
    INDIVIDUAL (não agrupado por mês do calendário) em toda a série
    histórica. Exclui o mês corrente (sempre incompleto), mesmo
    critério de totais_anuais. Base tanto de
    normais_climatologicas_mensais (agrupada por mês do calendário)
    quanto de climate.municipio_indicators.recordes (mês mais
    chuvoso/seco JÁ REGISTRADO — precisa do total por mês individual,
    não da média por mês do calendário).
    """
    hoje = timezone.localdate()
    linhas = (
        ChirpsData.objects.filter(municipio=municipio)
        .annotate(mes_ano=TruncMonth("date"))
        .values("mes_ano")
        .annotate(total=Sum("value"))
        .order_by("mes_ano")
    )
    return {
        linha["mes_ano"]: linha["total"]
        for linha in linhas
        if not (linha["mes_ano"].year == hoje.year and linha["mes_ano"].month == hoje.month)
    }


def normais_climatologicas_mensais(municipio):
    """
    dict {mes (1-12): {"media", "mediana", "p25", "p75", "minimo",
    "maximo", "n_anos"}} — estatística dos totais mensais de chuva
    agrupados por mês do calendário, em todos os anos históricos
    disponíveis. Mês com menos de MINIMO_ANOS_NORMAL_CLIMATOLOGICA anos
    de amostra fica de fora do dict (dado insuficiente pra uma normal
    climatológica confiável).
    """
    totais_por_mes = defaultdict(list)
    for data, total in totais_mensais(municipio).items():
        totais_por_mes[data.month].append(total)

    resultado = {}
    for mes, valores in totais_por_mes.items():
        if len(valores) < MINIMO_ANOS_NORMAL_CLIMATOLOGICA:
            continue
        p25, _, p75 = statistics.quantiles(valores, n=4)
        resultado[mes] = {
            "media": statistics.mean(valores),
            "mediana": statistics.median(valores),
            "p25": p25,
            "p75": p75,
            "minimo": min(valores),
            "maximo": max(valores),
            "n_anos": len(valores),
        }
    return resultado


def cenarios_futuros(municipio, meses=MESES_CENARIO_FUTURO):
    """
    Cenário "seco"/"normal"/"úmido" pra cada um dos próximos `meses`
    meses do calendário, lido das normais climatológicas (percentil
    25, mediana, percentil 75 do histórico do mesmo mês). NÃO é uma
    previsão de modelo climático — é "o que normalmente chove nesse
    mês, historicamente". Mês sem normal climatológica calculável
    (histórico curto) fica de fora da lista.
    """
    normais = normais_climatologicas_mensais(municipio)
    if not normais:
        return []

    hoje = timezone.localdate()
    resultado = []
    ano, mes = hoje.year, hoje.month
    for _ in range(meses):
        mes += 1
        if mes > 12:
            mes = 1
            ano += 1
        normal_do_mes = normais.get(mes)
        if normal_do_mes is None:
            continue
        resultado.append({
            "date": timezone.datetime(ano, mes, 1).date(),
            "seco": normal_do_mes["p25"],
            "normal": normal_do_mes["mediana"],
            "umido": normal_do_mes["p75"],
            "n_anos": normal_do_mes["n_anos"],
        })
    return resultado
