# spi/services.py
"""
Cálculo do SPI — Índice de Precipitação Padronizada (Etapa 7.1).

Fórmula do PDF de requisitos: SPI = (Xi - X̄) / σ — um z-score simples,
não o ajuste por distribuição Gama do método McKee "completo". Segue o
que o PDF pede literalmente, sem inventar complexidade que não foi
pedida (e sem precisar de scipy).

FONTE DO DADO: só o CHIRPS (climate.ChirpsData) tem histórico longo o
bastante (décadas) pra calcular uma média/desvio-padrão climatológicos
confiáveis. RainfallData (lançamento manual/estação do usuário) ainda
não tem série longa o suficiente pra isso — não é usado aqui.
CONSEQUÊNCIA DIRETA: SPI só é calculável para municípios com
`ativo=True` (hoje: Tangará da Serra e Cáceres) — não por estarem
citados em código nenhum lugar, mas porque só esses têm CHIRPS
importado. Ver docs/DECISOES.md.

MÉTODO:
1. Agrega ChirpsData (diário) em totais MENSAIS por município.
2. Pra cada escala (3/6/12 meses), calcula a soma corrente (rolling)
   dos últimos N meses, terminando em cada mês da série.
3. Agrupa esses valores por MÊS DO CALENDÁRIO (ex.: todos os "SPI-3
   terminando em março", de todos os anos) — essa é a distribuição
   climatológica de referência daquele mês/escala.
4. Padroniza (z-score) cada valor contra a média/desvio-padrão do seu
   próprio grupo de mês.
5. Classifica em 6 categorias (extremamente_umido ... seca_extrema) —
   os limiares numéricos não vêm no PDF (só os nomes das categorias),
   usei os limiares padrão da literatura (McKee et al. 1993), fundindo
   "moderadamente úmido" em "muito_umido" pra caber nas 6 categorias
   que o model já define. Ver docs/DECISOES.md.
"""
import statistics
from collections import defaultdict

from django.db.models import Sum
from django.db.models.functions import TruncMonth

from climate.models import ChirpsData

ESCALAS_VALIDAS = (3, 6, 12)

# Mínimo de anos de histórico no mesmo mês do calendário pra considerar a
# média/desvio-padrão climatológicos confiáveis. Menos que isso, o SPI
# calculado seria estatisticamente pouco confiável (não é limiar oficial
# de nenhuma norma — é uma escolha conservadora deste projeto).
MINIMO_ANOS_HISTORICO = 10

LIMIARES_CLASSIFICACAO = [
    (2.0, "extremamente_umido"),
    (1.5, "muito_umido"),
    (1.0, "moderadamente_umido"),
    (-1.0, "normal"),
    (-1.5, "seca_moderada"),
    (-2.0, "seca_severa"),
]


def classificar_spi(valor):
    """Aplica os limiares de cima pra baixo; o que sobrar é seca_extrema."""
    for limiar, categoria in LIMIARES_CLASSIFICACAO:
        if valor >= limiar:
            return categoria
    return "seca_extrema"


def _totais_mensais(municipio):
    """dict {date(primeiro dia do mês): total_mm} a partir do ChirpsData diário."""
    linhas = (
        ChirpsData.objects.filter(municipio=municipio)
        .annotate(mes=TruncMonth("date"))
        .values("mes")
        .annotate(total=Sum("value"))
        .order_by("mes")
    )
    return {linha["mes"]: linha["total"] for linha in linhas}


def _proximo_mes(mes):
    """Primeiro dia do mês seguinte — evita depender de python-dateutil só pra isso."""
    if mes.month == 12:
        return mes.replace(year=mes.year + 1, month=1)
    return mes.replace(month=mes.month + 1)


def _somas_moveis(totais_mensais, escala):
    """
    Lista de (mes_final, soma) para cada janela de `escala` meses
    CONSECUTIVOS (sem buraco) encontrada na série. Meses fora de sequência
    (buraco de dado) simplesmente não geram uma janela válida ali.
    """
    meses_ordenados = sorted(totais_mensais.keys())
    resultado = []

    for indice in range(escala - 1, len(meses_ordenados)):
        janela = meses_ordenados[indice - escala + 1 : indice + 1]
        # Confere contiguidade: cada mês da janela é exatamente 1 mês
        # depois do anterior (senão, tem buraco no meio e a soma não
        # representa os `escala` meses corretos).
        contigua = all(
            janela[i] == _proximo_mes(janela[i - 1]) for i in range(1, len(janela))
        )
        if not contigua:
            continue

        soma = sum(totais_mensais[mes] for mes in janela)
        resultado.append((janela[-1], soma))

    return resultado


def calcular_serie_spi(municipio, escala):
    """
    Retorna lista de dicts {"date": date, "value": float, "classification": str}
    — um por mês final de janela, para todos os meses onde há histórico
    suficiente (MINIMO_ANOS_HISTORICO) no mesmo mês do calendário.
    """
    if escala not in ESCALAS_VALIDAS:
        raise ValueError(f"Escala inválida: {escala}. Use {ESCALAS_VALIDAS}.")

    totais = _totais_mensais(municipio)
    if not totais:
        return []

    somas = _somas_moveis(totais, escala)

    # Agrupa por mês do calendário (1-12) — a distribuição de referência
    # do SPI é "todos os SPI-N terminando em [mês X]", não a série toda junta.
    por_mes_calendario = defaultdict(list)
    for mes_final, soma in somas:
        por_mes_calendario[mes_final.month].append((mes_final, soma))

    resultado = []
    for mes_calendario, valores in por_mes_calendario.items():
        if len(valores) < MINIMO_ANOS_HISTORICO:
            continue  # histórico curto demais pra esse mês/escala — não calcula

        amostras = [soma for _mes, soma in valores]
        media = statistics.mean(amostras)
        desvio = statistics.stdev(amostras)
        if desvio == 0:
            continue  # sem variação nenhuma na amostra — z-score indefinido

        for mes_final, soma in valores:
            z = (soma - media) / desvio
            resultado.append({
                "date": mes_final,
                "value": z,
                "classification": classificar_spi(z),
            })

    resultado.sort(key=lambda item: item["date"])
    return resultado
