# climate/validation.py
"""
Validação estatística CHIRPS × dado local (Etapa 7.2). Métricas do PDF:
R², RMSE, MAE, MBE, índice d (Willmott, 1981) e índice c (Camargo &
Sentelhas, 1997 — padrão usado em agrometeorologia no Brasil).

COMPARAÇÃO: pra cada dia em que a estação tem um dado LOCAL (lançado
manualmente ou importado — não CHIRPS) e o CHIRPS do município da
fazenda dela também tem valor nesse mesmo dia, forma-se um par
(chirps, local). As métricas vêm desses pares.

CONSEQUÊNCIA PRÁTICA: só existe CHIRPS pra municípios `ativo=True`
(mesma restrição de dado da Etapa 3/7.1, não uma limitação deste
código) — uma estação fora de Tangará da Serra/Cáceres hoje não tem
com o que comparar ainda, mesmo que já tenha dado local lançado.
"""
import statistics

from .models import ChirpsData, RainfallData

MINIMO_PARES = 3  # abaixo disso, correlação/desvio-padrão não são confiáveis

FAIXAS_DESEMPENHO_C = [
    (0.85, "otimo"),
    (0.76, "muito_bom"),
    (0.66, "bom"),
    (0.61, "mediano"),
    (0.51, "sofrivel"),
    (0.41, "mau"),
]


def classificar_indice_c(c):
    for limiar, categoria in FAIXAS_DESEMPENHO_C:
        if c >= limiar:
            return categoria
    return "pessimo"


def pares_chirps_local(station):
    """
    Lista de (valor_chirps, valor_local) para os dias em que existem os
    dois — CHIRPS do município da fazenda da estação, dado local da
    própria estação (qualquer origem exceto 'chirps').
    """
    municipio = station.farm.municipio

    locais = {
        registro.date: registro.value
        for registro in RainfallData.objects.filter(station=station).exclude(source_type="chirps")
    }
    if not locais:
        return []

    chirps = {
        registro.date: registro.value
        for registro in ChirpsData.objects.filter(municipio=municipio, date__in=locais.keys())
    }

    return [(chirps[data], locais[data]) for data in sorted(locais) if data in chirps]


def calcular_metricas(pares):
    """
    pares: lista de (chirps, local). Retorna dict com as métricas, ou
    None se não houver pares suficientes (MINIMO_PARES).
    """
    if len(pares) < MINIMO_PARES:
        return None

    valores_chirps = [par[0] for par in pares]
    valores_locais = [par[1] for par in pares]
    n = len(pares)

    media_local = statistics.mean(valores_locais)

    diferencas = [chirps - local for chirps, local in pares]
    rmse = (sum(diferenca ** 2 for diferenca in diferencas) / n) ** 0.5
    mae = sum(abs(diferenca) for diferenca in diferencas) / n
    mbe = sum(diferencas) / n

    # Índice d (Willmott, 1981): 1 - [Σ(P-O)²] / [Σ(|P-Ō|+|O-Ō|)²]
    soma_erro_quadratico = sum((chirps - local) ** 2 for chirps, local in pares)
    soma_potencial = sum(
        (abs(chirps - media_local) + abs(local - media_local)) ** 2 for chirps, local in pares
    )
    if soma_potencial == 0:
        # Só acontece se CHIRPS e local forem idênticos e constantes em
        # todos os pares — concordância perfeita, sem erro nenhum.
        indice_d = 1.0
    else:
        indice_d = 1 - (soma_erro_quadratico / soma_potencial)

    # Correlação de Pearson (r); R² = r². Série constante -> correlação
    # indefinida, tratamos como 0 (sem relação linear detectável).
    if statistics.pstdev(valores_chirps) == 0 or statistics.pstdev(valores_locais) == 0:
        r = 0.0
    else:
        r = statistics.correlation(valores_chirps, valores_locais)
    r2 = r ** 2

    # Índice c (Camargo & Sentelhas, 1997) = r × d
    indice_c = r * indice_d

    return {
        "n_pares": n,
        "r2": r2,
        "rmse": rmse,
        "mae": mae,
        "mbe": mbe,
        "indice_d": indice_d,
        "indice_c": indice_c,
        "desempenho_c": classificar_indice_c(indice_c),
    }
