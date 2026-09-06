# climate/calculadora_validacao.py
"""
Calculadora de validação CHIRPS × pluviômetro pra pesquisadores — a
metodologia do Artigo 1 (Etapa 7.2, climate/validation.py) virando
ferramenta pública: o pesquisador sobe um arquivo com a chuva medida no
pluviômetro dele, o sistema cruza com o CHIRPS do MUNICÍPIO escolhido
(não coordenada exata — ver docs/DECISOES.md sobre por quê) e devolve
as mesmas métricas (R², RMSE, MAE, MBE, índice d, índice c).

REAPROVEITAMENTO — nenhuma métrica nem parser novo aqui:
- climate.data_import.processar_arquivo faz o parse do .csv/.xlsx
  (fora deste módulo, chamado pela view).
- climate.validation.calcular_metricas calcula as métricas (mesma
  função usada pela Etapa 7.2, sem duplicar fórmula nenhuma).
- climate.trends.totais_mensais agrega o CHIRPS por mês (reaproveitado
  pro caso de granularidade mensal).

Só duas coisas são novas: detectar se o arquivo do usuário é diário ou
mensal, e parear esse arquivo com o CHIRPS do município (o pareamento
que já existe, `validation.pares_chirps_local`, espera uma `Station`
cadastrada — aqui não há estação nenhuma, é um arquivo solto).
"""
import statistics
from collections import defaultdict

from . import trends
from .models import ChirpsData
from .validation import MINIMO_PARES, calcular_metricas

# Abaixo disso, a validação "funciona" (MINIMO_PARES já garante isso),
# mas a amostra é pequena demais pra ser estatisticamente representativa
# — não bloqueia (a literatura de validação sempre reporta o n, cabe a
# quem lê decidir), só avisa com destaque. Limiar empírico deste
# projeto, sem referência publicada (mesmo espírito de outros limiares
# já documentados em spi/services.py e climate/quality_checks.py).
MINIMO_PARES_AMOSTRA_CONFIAVEL = 30


def detectar_granularidade(registros):
    """
    "diaria" ou "mensal", a partir da MEDIANA do intervalo (em dias)
    entre datas consecutivas já ordenadas — pluviômetro diário tem
    mediana ~1 dia; totais mensais têm mediana ~28-31 dias. Usa mediana
    (não média) pra não ser distorcido por um gap ocasional (ex.: mês
    sem lançamento no meio de uma série diária). None se não der pra
    decidir (menos de 2 datas distintas).
    """
    datas = sorted(set(registro["date"] for registro in registros))
    if len(datas) < 2:
        return None

    intervalos = [(datas[i] - datas[i - 1]).days for i in range(1, len(datas))]
    mediana = statistics.median(intervalos)

    return "mensal" if mediana >= 20 else "diaria"


def parear_diario(registros, municipio):
    """[(data, chirps, local), ...] — casa cada registro do usuário (por
    data exata) com o CHIRPS do município nesse mesmo dia. Duplicata de
    data no arquivo do usuário (não deveria acontecer, mas não é papel
    deste módulo validar isso) usa o último valor lido pra aquela data."""
    locais = {registro["date"]: registro["value"] for registro in registros}
    chirps = {
        registro.date: registro.value
        for registro in ChirpsData.objects.filter(municipio=municipio, date__in=locais.keys())
    }
    return [(data, chirps[data], locais[data]) for data in sorted(locais) if data in chirps]


def parear_mensal(registros, municipio):
    """
    [(mes, chirps, local), ...] — soma o arquivo do usuário por (ano,
    mês) (caso venha mais de uma linha no mesmo mês, incomum mas não
    proibido) e pareia contra climate.trends.totais_mensais (total do
    CHIRPS por mês individual, já existe, não recalculado aqui). `mes`
    é o primeiro dia do mês (date), mesma convenção de totais_mensais.
    """
    locais_por_mes = defaultdict(float)
    for registro in registros:
        chave = registro["date"].replace(day=1)
        locais_por_mes[chave] += registro["value"]

    totais_chirps = trends.totais_mensais(municipio)
    return [
        (mes, totais_chirps[mes], locais_por_mes[mes])
        for mes in sorted(locais_por_mes)
        if mes in totais_chirps
    ]


def histograma_diferencas(pares, n_faixas=10):
    """
    Distribuição das diferenças (CHIRPS - medido) em N faixas de largura
    igual (amplitude mínimo-máximo dividida em partes) — pro gráfico de
    distribuição do erro. N_FAIXAS fixo em 10, escolha simples (não é
    uma regra estatística tipo Sturges) que se comporta bem tanto com
    poucos quanto com muitos pares.

    Retorna [{"inicio": float, "fim": float, "contagem": int}, ...], com
    N_FAIXAS itens — exceto quando todas as diferenças são idênticas
    (uma faixa só, sem dividir por zero).
    """
    diferencas = [chirps - local for _data, chirps, local in pares]
    if not diferencas:
        return []

    minimo, maximo = min(diferencas), max(diferencas)
    if minimo == maximo:
        return [{"inicio": minimo, "fim": maximo, "contagem": len(diferencas)}]

    largura = (maximo - minimo) / n_faixas
    faixas = [
        {"inicio": minimo + indice * largura, "fim": minimo + (indice + 1) * largura, "contagem": 0}
        for indice in range(n_faixas)
    ]
    for diferenca in diferencas:
        indice = min(int((diferenca - minimo) / largura), n_faixas - 1)
        faixas[indice]["contagem"] += 1
    return faixas


def calcular_validacao(registros, municipio):
    """
    Orquestra: detecta granularidade → pareia → calcula métricas
    (climate.validation.calcular_metricas, sem duplicar fórmula) →
    monta o histograma do erro (só binning, não é uma métrica nova).

    Retorna {"granularidade": "diaria"|"mensal"|None, "pares": [(data,
    chirps, local), ...], "metricas": dict|None, "amostra_pequena":
    bool, "histograma": [...]}. "metricas" vem None se não houver
    MINIMO_PARES pares em comum (validation.py já garante essa
    checagem) — "amostra_pequena" é True quando o resultado EXISTE mas
    tem menos de MINIMO_PARES_AMOSTRA_CONFIAVEL pares (mostra o
    resultado, só avisa — nunca esconde). "histograma" vem [] no mesmo
    caso de "metricas" None (nada pra distribuir).

    `pares` guarda a DATA junto (útil pra tabela/gráfico/exportação),
    mas climate.validation.calcular_metricas continua recebendo só os
    pares (chirps, local) — sua assinatura não muda.
    """
    granularidade = detectar_granularidade(registros)
    if granularidade is None:
        return {"granularidade": None, "pares": [], "metricas": None, "amostra_pequena": False, "histograma": []}

    pares = parear_diario(registros, municipio) if granularidade == "diaria" else parear_mensal(registros, municipio)
    metricas = calcular_metricas([(chirps, local) for _data, chirps, local in pares])

    return {
        "granularidade": granularidade,
        "pares": pares,
        "metricas": metricas,
        "amostra_pequena": bool(metricas) and metricas["n_pares"] < MINIMO_PARES_AMOSTRA_CONFIAVEL,
        "histograma": histograma_diferencas(pares) if metricas else [],
    }
