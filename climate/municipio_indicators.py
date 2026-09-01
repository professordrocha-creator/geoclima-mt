# climate/municipio_indicators.py
"""
Indicadores climáticos POR MUNICÍPIO, calculados direto do CHIRPS
(climate.ChirpsData) — independente de existir fazenda ou estação
cadastrada. Pensado pra ser reaproveitado nos dois contextos: a home
pública (município escolhido no mapa, sem login) e o painel privado de
fazenda (resolvendo farm.municipio e chamando as mesmas funções).

DECISÃO DE ARQUITETURA (ver docs/DECISOES.md): zero model novo, zero
migration. Segue exatamente o padrão já usado em climate/trends.py —
toda função recebe `municipio` (objeto Municipio OU codigo_ibge em
string, resolvido por _resolver_municipio) e calcula ON-THE-FLY sobre
ChirpsData. Nada é persistido; o "cache" é só uma camada de
performance opcional (Redis, TTL de 1 dia — CHIRPS só atualiza 1x/dia
via atualizar_chirps, 04:00), não uma fonte de verdade.

REAPROVEITAMENTO — nenhuma lógica de cálculo é duplicada aqui:
- SPI (1/3/6/12): spi.services.calcular_serie_spi (já recebe município
  diretamente — só a ESCALAS_VALIDAS de lá ganhou o valor 1, ver
  spi/services.py).
- Climatologia mensal: climate.trends.normais_climatologicas_mensais.
- Limiar de "histórico confiável" pra anomalia/percentil: reaproveita
  climate.trends.MINIMO_ANOS_NORMAL_CLIMATOLOGICA (mesma família
  estatística — normal climatológica —, não o limiar mais rígido do
  SPI).

FASE 1 (SPI, climatologia, anomalia, percentil, acumulados) documentada
acima. FASE 2 (veranico, dias chuvosos, intensidade, recordes,
tendência) segue o mesmo padrão — reaproveita climate.trends.totais_anuais
e a nova climate.trends.totais_mensais (extraída de
normais_climatologicas_mensais nesta mesma leva, pra recordes usar sem
duplicar a query). A tendência de longo prazo usa Mann-Kendall + Sen's
slope (não a regressão linear simples de tendencia_anual, que continua
existindo — tendencia_anual não foi alterada nem removida) — método
padrão pra séries climáticas: testa significância estatística, não só
ajusta uma reta. Implementado com `statistics`/`math` puros da stdlib
(inclusive `math.erfc` pra distribuição normal do p-valor) — zero
dependência nova, nem numpy. Ver docs/DECISOES.md pras fórmulas e a
validação com série sintética.
"""
import math
import statistics
from datetime import timedelta

from django.core.cache import cache
from django.db.models import Sum
from django.db.models.functions import TruncYear
from django.utils import timezone

from maps.models import Municipio
from spi.services import ESCALAS_VALIDAS as ESCALAS_SPI
from spi.services import calcular_serie_spi

from . import trends
from .models import ChirpsData
from .trends import MINIMO_ANOS_NORMAL_CLIMATOLOGICA, MINIMO_ANOS_TENDENCIA

# Liga/desliga o cache Redis sem mexer no corpo das funções — útil pra
# testar o cálculo "cru" (garantir que o número está certo antes de
# confiar que o cache não está escondendo um valor velho). Trocar aqui
# ou, se preferir sem editar código, dá pra futuramente ler de env var.
CACHE_HABILITADO = True

CACHE_TTL_SEGUNDOS = 60 * 60 * 24  # 1 dia — CHIRPS só atualiza 1x/dia
CACHE_PREFIXO = "municipio_indicators"

JANELAS_ACUMULADO_DIAS = (7, 30, 90)


def _resolver_municipio(municipio):
    """Aceita um objeto Municipio OU seu codigo_ibge (string) — mesma
    flexibilidade que a home pública precisa (recebe codigo_ibge do
    mapa) e o painel privado (já tem farm.municipio carregado)."""
    if isinstance(municipio, str):
        return Municipio.objects.get(codigo_ibge=municipio)
    return municipio


def _cache_key(nome_funcao, codigo_ibge, *partes):
    sufixo = ":".join(str(parte) for parte in partes)
    chave = f"{CACHE_PREFIXO}:{nome_funcao}:{codigo_ibge}"
    return f"{chave}:{sufixo}" if sufixo else chave


def _com_cache(chave, calcular):
    """
    cache.get()/set() em volta de `calcular` (uma função sem argumento,
    normalmente um lambda) — só ativa se CACHE_HABILITADO. Resultado
    None (função não achou dado suficiente) nunca é cacheado de
    propósito: é barato recalcular um "sem dado" comparado ao risco de
    esconder por até 1 dia um resultado que passou a existir (ex.:
    CHIRPS que acabou de ser importado pro município).
    """
    if not CACHE_HABILITADO:
        return calcular()

    resultado = cache.get(chave)
    if resultado is None:
        resultado = calcular()
        if resultado is not None:
            cache.set(chave, resultado, CACHE_TTL_SEGUNDOS)
    return resultado


def _ultimo_mes_completo():
    """(ano, mes) do último mês CIVIL completo — exclui o mês corrente
    (sempre parcial), mesmo critério de totais_anuais/normais_climatologicas
    em climate/trends.py."""
    hoje = timezone.localdate()
    ano, mes = hoje.year, hoje.month - 1
    if mes == 0:
        ano, mes = ano - 1, 12
    return ano, mes


def _totais_do_mes_por_ano(municipio, mes):
    """
    dict {ano: total_mm} — o total de chuva do mês `mes` (1-12) do
    município, em CADA ano do histórico. Base pra anomalia e percentil:
    ambos comparam "este ano" contra "todos os outros anos, no mesmo
    mês do calendário" (mesma lógica de agrupamento do SPI/normais
    climatológicas, só que aqui expõe o valor por ano em vez de só a
    estatística agregada).
    """
    linhas = (
        ChirpsData.objects.filter(municipio=municipio, date__month=mes)
        .annotate(ano=TruncYear("date"))
        .values("ano")
        .annotate(total=Sum("value"))
        .order_by("ano")
    )
    return {linha["ano"].year: linha["total"] for linha in linhas}


# ---------------------------------------------------------------------
# SPI (1/3/6/12) — reaproveita spi.services.calcular_serie_spi inteiro.
# ---------------------------------------------------------------------

def spi_serie(municipio, escala):
    """Série completa de SPI-`escala` do município (lista de dicts
    date/value/classification) — mesmo formato de calcular_serie_spi."""
    municipio = _resolver_municipio(municipio)
    if escala not in ESCALAS_SPI:
        raise ValueError(f"Escala inválida: {escala}. Use {ESCALAS_SPI}.")

    chave = _cache_key("spi_serie", municipio.codigo_ibge, escala)
    return _com_cache(chave, lambda: calcular_serie_spi(municipio, escala))


def spi_atual(municipio, escala):
    """Último valor de SPI-`escala` do município, ou None se não houver
    histórico suficiente ainda (ver MINIMO_ANOS_HISTORICO em spi/services.py)."""
    serie = spi_serie(municipio, escala)
    return serie[-1] if serie else None


# ---------------------------------------------------------------------
# Climatologia mensal — reaproveita climate.trends inteiro.
# ---------------------------------------------------------------------

def climatologia_mensal(municipio):
    """dict {mes: {media, mediana, p25, p75, minimo, maximo, n_anos}} —
    repassa direto pra climate.trends.normais_climatologicas_mensais,
    só adicionando cache."""
    municipio = _resolver_municipio(municipio)
    chave = _cache_key("climatologia_mensal", municipio.codigo_ibge)
    return _com_cache(chave, lambda: trends.normais_climatologicas_mensais(municipio))


# ---------------------------------------------------------------------
# Anomalia (absoluta e percentual) — novo.
# ---------------------------------------------------------------------

def anomalia_mensal(municipio, ano=None, mes=None):
    """
    Compara a chuva de um mês específico (padrão: último mês civil
    completo) contra a média histórica DO MESMO MÊS DO CALENDÁRIO nos
    outros anos (o ano avaliado é excluído do cálculo da própria
    média, pra não se comparar consigo mesmo).

    Retorna None se não houver dado CHIRPS pro (município, ano, mês)
    pedido, ou se sobrarem menos de MINIMO_ANOS_NORMAL_CLIMATOLOGICA
    anos de comparação.
    """
    municipio = _resolver_municipio(municipio)
    if ano is None or mes is None:
        ano, mes = _ultimo_mes_completo()

    chave = _cache_key("anomalia_mensal", municipio.codigo_ibge, ano, mes)

    def _calcular():
        totais_por_ano = _totais_do_mes_por_ano(municipio, mes)
        chuva_atual = totais_por_ano.get(ano)
        if chuva_atual is None:
            return None

        historico = {a: t for a, t in totais_por_ano.items() if a != ano}
        if len(historico) < MINIMO_ANOS_NORMAL_CLIMATOLOGICA:
            return None

        media_historica = statistics.mean(historico.values())
        anomalia_percentual = (
            (chuva_atual / media_historica * 100) if media_historica > 0 else None
        )

        return {
            "ano": ano,
            "mes": mes,
            "chuva_mm": chuva_atual,
            "media_historica_mm": media_historica,
            "anomalia_absoluta_mm": chuva_atual - media_historica,
            "anomalia_percentual": anomalia_percentual,
            "n_anos_historico": len(historico),
        }

    return _com_cache(chave, _calcular)


# ---------------------------------------------------------------------
# Percentil histórico — novo.
# ---------------------------------------------------------------------

def percentil_historico_mensal(municipio, ano=None, mes=None):
    """
    Onde a chuva de um mês específico (padrão: último mês civil
    completo) se posiciona na distribuição histórica DO MESMO MÊS DO
    CALENDÁRIO (todos os anos, incluindo o próprio ano avaliado dessa
    vez — diferente da anomalia, aqui o ano faz parte da distribuição
    que está sendo ranqueada).

    `percentil`: 0 = o mês mais seco já registrado, 100 = o mais
    chuvoso. `posicao_mais_seco`: 1 = o mais seco (ranking ordinal,
    mais intuitivo pra texto tipo "3º mês de julho mais seco desde
    1998"). Empates exatos (raros com float de mm) ficam com a mesma
    contagem de "mais secos que este".

    None se não houver dado pro (município, ano, mês) pedido, ou menos
    de MINIMO_ANOS_NORMAL_CLIMATOLOGICA anos no histórico.
    """
    municipio = _resolver_municipio(municipio)
    if ano is None or mes is None:
        ano, mes = _ultimo_mes_completo()

    chave = _cache_key("percentil_historico_mensal", municipio.codigo_ibge, ano, mes)

    def _calcular():
        totais_por_ano = _totais_do_mes_por_ano(municipio, mes)
        chuva_atual = totais_por_ano.get(ano)
        if chuva_atual is None or len(totais_por_ano) < MINIMO_ANOS_NORMAL_CLIMATOLOGICA:
            return None

        valores = list(totais_por_ano.values())
        n = len(valores)
        mais_secos_que_este = sum(1 for v in valores if v < chuva_atual)
        posicao_mais_seco = mais_secos_que_este + 1
        percentil = (mais_secos_que_este / (n - 1) * 100) if n > 1 else 50.0

        return {
            "ano": ano,
            "mes": mes,
            "chuva_mm": chuva_atual,
            "percentil": percentil,
            "posicao_mais_seco": posicao_mais_seco,
            "posicao_mais_chuvoso": n - posicao_mais_seco + 1,
            "n_anos_historico": n,
            "primeiro_ano_historico": min(totais_por_ano),
        }

    return _com_cache(chave, _calcular)


# ---------------------------------------------------------------------
# Acumulados 7/30/90 dias — novo (só a parte CHIRPS, sem misturar com
# dado local de fazenda — essa mistura é responsabilidade de
# dashboard.services.acumulados, não tocado).
# ---------------------------------------------------------------------

def acumulados_municipio(municipio):
    """Lista [{dias, chirps_mm}, ...] pras janelas de JANELAS_ACUMULADO_DIAS,
    contando pra trás a partir de hoje. chirps_mm é None se não houver
    nenhum registro CHIRPS na janela (município sem dado importado)."""
    municipio = _resolver_municipio(municipio)
    chave = _cache_key("acumulados", municipio.codigo_ibge)

    def _calcular():
        hoje = timezone.localdate()
        resultado = []
        for dias in JANELAS_ACUMULADO_DIAS:
            desde = hoje - timedelta(days=dias)
            total = (
                ChirpsData.objects.filter(municipio=municipio, date__gte=desde)
                .aggregate(total=Sum("value"))["total"]
            )
            resultado.append({
                "dias": dias,
                "chirps_mm": round(total, 1) if total is not None else None,
            })
        return resultado

    return _com_cache(chave, _calcular)


# =======================================================================
# FASE 2 — veranico, dias chuvosos, intensidade, recordes, tendência.
# =======================================================================

LIMIAR_DIA_SECO_MM = 1.0  # dia seco = chuva < 1mm (complementar a dia chuvoso = chuva > 1mm)
LIMIARES_DIA_CHUVOSO_MM = (1, 5, 10)


def _dias_sao_consecutivos(data_anterior, data_atual):
    return (data_atual - data_anterior).days == 1


def _maior_sequencia_em_lista(registros):
    """
    {"dias", "inicio", "fim"} da maior sequência de dias CONSECUTIVOS
    (checa contiguidade real de data, não assume ausência de buraco)
    com chuva < LIMIAR_DIA_SECO_MM, numa lista JÁ ORDENADA por data de
    (data, valor). None se não houver nenhum dia seco na lista.

    Núcleo extraído de _maior_sequencia_seca (que opera sobre um
    período contínuo) pra ser reaproveitado também pela série anual
    (mesma lógica, uma lista por ano — ver veranico_maximo_serie_anual).
    """
    if not registros:
        return None

    maior_dias, maior_inicio, maior_fim = 0, None, None
    seq_inicio, seq_tamanho = None, 0
    data_anterior = None
    dia_anterior_seco = False

    for data, valor in registros:
        # "Contíguo" só importa se o dia ANTERIOR também era seco — data
        # consecutiva sozinha não continua sequência nenhuma se ontem
        # tinha chovido (bug corrigido depois de ver "inicio" sempre None
        # no teste com dado real: a condição original só checava a data
        # ser consecutiva, não se o dia anterior estava na sequência seca).
        contiguo = data_anterior is not None and _dias_sao_consecutivos(data_anterior, data)
        seco = valor < LIMIAR_DIA_SECO_MM

        if seco and contiguo and dia_anterior_seco:
            seq_tamanho += 1
        elif seco:
            seq_inicio, seq_tamanho = data, 1
        else:
            seq_inicio, seq_tamanho = None, 0

        if seco and seq_tamanho > maior_dias:
            maior_dias, maior_inicio, maior_fim = seq_tamanho, seq_inicio, data

        data_anterior = data
        dia_anterior_seco = seco

    if maior_dias == 0:
        return None
    return {"dias": maior_dias, "inicio": maior_inicio, "fim": maior_fim}


def _maior_sequencia_seca(municipio, desde=None):
    """{"dias", "inicio", "fim"} da maior sequência seca no período
    pedido (desde=None = toda a série) — ver _maior_sequencia_em_lista."""
    qs = ChirpsData.objects.filter(municipio=municipio)
    if desde:
        qs = qs.filter(date__gte=desde)
    registros = list(qs.order_by("date").values_list("date", "value"))
    return _maior_sequencia_em_lista(registros)


def veranico(municipio):
    """
    {"recente_12_meses": {...}, "recorde_historico": {...}} — maior
    sequência de dias secos consecutivos (chuva < 1mm). Descrito de
    forma neutra ("dias secos consecutivos"), sem linguagem
    agronômica prescritiva — a leitura de impacto na lavoura é de
    quem consome o dado, não do sistema. None se não houver CHIRPS
    suficiente pro município.
    """
    municipio = _resolver_municipio(municipio)
    chave = _cache_key("veranico", municipio.codigo_ibge)

    def _calcular():
        recorde = _maior_sequencia_seca(municipio)
        if recorde is None:
            return None
        desde_recente = timezone.localdate() - timedelta(days=365)
        recente = _maior_sequencia_seca(municipio, desde=desde_recente)
        return {"recente_12_meses": recente, "recorde_historico": recorde}

    return _com_cache(chave, _calcular)


def _ultimo_ano_completo():
    return timezone.localdate().year - 1  # mesmo critério de totais_anuais


def _valores_diarios_do_ano(municipio, ano):
    return list(
        ChirpsData.objects.filter(municipio=municipio, date__year=ano).values_list("value", flat=True)
    )


def dias_chuvosos(municipio, ano=None):
    """
    {"ano", "limiares": {"1": n, "5": n, "10": n}, "total_dias_com_registro"}
    — contagem de dias com chuva acima de cada limiar em
    LIMIARES_DIA_CHUVOSO_MM, no ano civil completo mais recente por
    padrão (mesmo critério de totais_anuais). None sem CHIRPS pro ano.
    """
    municipio = _resolver_municipio(municipio)
    if ano is None:
        ano = _ultimo_ano_completo()
    chave = _cache_key("dias_chuvosos", municipio.codigo_ibge, ano)

    def _calcular():
        valores = _valores_diarios_do_ano(municipio, ano)
        if not valores:
            return None
        return {
            "ano": ano,
            "limiares": {
                str(limiar): sum(1 for v in valores if v > limiar)
                for limiar in LIMIARES_DIA_CHUVOSO_MM
            },
            "total_dias_com_registro": len(valores),
        }

    return _com_cache(chave, _calcular)


def intensidade_chuva(municipio, ano=None):
    """
    {"ano", "total_mm", "dias_com_chuva", "intensidade_mm_por_dia_chuvoso"}
    — total do ano dividido pelos dias com chuva > 1mm: indica se a
    chuva é concentrada (poucos dias, alta intensidade) ou distribuída
    (muitos dias, baixa intensidade). Mesmo ano padrão de
    dias_chuvosos. None sem CHIRPS pro ano.
    """
    municipio = _resolver_municipio(municipio)
    if ano is None:
        ano = _ultimo_ano_completo()
    chave = _cache_key("intensidade_chuva", municipio.codigo_ibge, ano)

    def _calcular():
        valores = _valores_diarios_do_ano(municipio, ano)
        if not valores:
            return None
        dias_com_chuva = [v for v in valores if v > LIMIAR_DIA_SECO_MM]
        total_mm = sum(valores)
        return {
            "ano": ano,
            "total_mm": round(total_mm, 1),
            "dias_com_chuva": len(dias_com_chuva),
            "intensidade_mm_por_dia_chuvoso": (
                round(sum(dias_com_chuva) / len(dias_com_chuva), 2) if dias_com_chuva else None
            ),
        }

    return _com_cache(chave, _calcular)


def recordes(municipio):
    """
    {"ano_mais_chuvoso", "ano_mais_seco", "mes_mais_chuvoso",
    "mes_mais_seco", "n_anos_historico"} — extremos JÁ REGISTRADOS na
    série toda. Reaproveita climate.trends.totais_anuais (ano) e
    climate.trends.totais_mensais (mês individual — não a média por
    mês do calendário) — nenhum cálculo novo, só encontra o
    máximo/mínimo. None sem CHIRPS suficiente.
    """
    municipio = _resolver_municipio(municipio)
    chave = _cache_key("recordes", municipio.codigo_ibge)

    def _calcular():
        anuais = trends.totais_anuais(municipio)
        mensais = trends.totais_mensais(municipio)
        if not anuais or not mensais:
            return None

        ano_mais_chuvoso = max(anuais, key=anuais.get)
        ano_mais_seco = min(anuais, key=anuais.get)
        mes_mais_chuvoso = max(mensais, key=mensais.get)
        mes_mais_seco = min(mensais, key=mensais.get)

        return {
            "ano_mais_chuvoso": {"ano": ano_mais_chuvoso, "total_mm": round(anuais[ano_mais_chuvoso], 1)},
            "ano_mais_seco": {"ano": ano_mais_seco, "total_mm": round(anuais[ano_mais_seco], 1)},
            "mes_mais_chuvoso": {"date": mes_mais_chuvoso, "total_mm": round(mensais[mes_mais_chuvoso], 1)},
            "mes_mais_seco": {"date": mes_mais_seco, "total_mm": round(mensais[mes_mais_seco], 1)},
            "n_anos_historico": len(anuais),
        }

    return _com_cache(chave, _calcular)


# ---------------------------------------------------------------------
# Tendência de longo prazo — Mann-Kendall (direção + significância) +
# Sen's slope (magnitude). Método padrão pra séries climáticas — ao
# contrário da regressão linear simples (climate.trends.tendencia_anual,
# não alterada), testa se a tendência é estatisticamente significativa
# em vez de só ajustar uma reta que sempre "acha" alguma inclinação.
# Implementado com statistics/math puros da stdlib — math.erfc resolve
# a CDF da normal padrão sem precisar de scipy.stats.norm. Fórmulas e
# validação com série sintética em docs/DECISOES.md.
# ---------------------------------------------------------------------

def _mann_kendall_s_z_p(valores):
    """S (estatística), Z (normalizado, com correção de continuidade) e
    p-valor bicaudal (via erfc — equivalente à normal padrão)."""
    n = len(valores)
    s = sum(
        _sinal(valores[j] - valores[i])
        for i in range(n - 1)
        for j in range(i + 1, n)
    )

    # Correção de empates: agrupa valores repetidos (raro com float de
    # mm, mas a fórmula geral trata isso corretamente de qualquer jeito).
    contagens = {}
    for v in valores:
        contagens[v] = contagens.get(v, 0) + 1
    correcao_empates = sum(t * (t - 1) * (2 * t + 5) for t in contagens.values() if t > 1)

    var_s = (n * (n - 1) * (2 * n + 5) - correcao_empates) / 18
    if var_s <= 0:
        return s, 0.0, 1.0

    if s > 0:
        z = (s - 1) / math.sqrt(var_s)
    elif s < 0:
        z = (s + 1) / math.sqrt(var_s)
    else:
        z = 0.0

    p_valor = math.erfc(abs(z) / math.sqrt(2))
    return s, z, p_valor


def _sinal(x):
    return 1 if x > 0 else (-1 if x < 0 else 0)


def _sens_slope(x, y):
    """Mediana das inclinações par a par (Theil-Sen) + intercepto
    (mediana(y) - slope × mediana(x)) — estimador robusto de magnitude,
    não sensível a outliers como a regressão linear simples."""
    n = len(x)
    inclinacoes = [
        (y[j] - y[i]) / (x[j] - x[i])
        for i in range(n - 1)
        for j in range(i + 1, n)
    ]
    slope = statistics.median(inclinacoes)
    intercepto = statistics.median(y) - slope * statistics.median(x)
    return slope, intercepto


def _tendencia_de_serie(anos, valores):
    """
    Mann-Kendall + Sen's slope sobre uma série anual QUALQUER (anos e
    valores já alinhados, mesmo tamanho) — núcleo genérico extraído de
    tendencia_mann_kendall pra ser reaproveitado por qualquer indicador
    anual (hoje: total de chuva E intensidade; ver
    intensidade_serie_anual). None se menos de MINIMO_ANOS_TENDENCIA
    pontos — mesmo limiar em toda série anual deste módulo.

    "significativo": True se p_valor < 0.05. "direcao": "aumento"/
    "reducao"/"estavel" pelo sinal do slope (só interpretável em
    conjunto com "significativo" — um slope não-nulo sem significância
    estatística é ruído, não tendência).
    """
    if len(anos) < MINIMO_ANOS_TENDENCIA:
        return None

    s, z, p_valor = _mann_kendall_s_z_p(valores)
    slope, intercepto = _sens_slope(anos, valores)

    if slope > 0:
        direcao = "aumento"
    elif slope < 0:
        direcao = "reducao"
    else:
        direcao = "estavel"

    return {
        "anos": anos,
        "valores": valores,
        "slope_mm_por_ano": slope,
        "intercepto_sen": intercepto,
        "mann_kendall_s": s,
        "mann_kendall_z": z,
        "p_valor": p_valor,
        "significativo": p_valor < 0.05,
        "direcao": direcao,
        "n_anos": len(anos),
    }


def interpretar_tendencia(t, rotulo_aumento, rotulo_reducao, estavel_quando_nao_significativo):
    """
    Frase de interpretação HONESTA de um dict de _tendencia_de_serie —
    mesma regra de comunicação (e mesmos 3 casos) da função
    `renderizarDestaqueTendencia` em core/templates/core/index.html:
    nunca dá a entender tendência onde o teste não sustenta. Pública
    (sem underscore) porque climate.municipio_exports reaproveita pra
    escrever a coluna "Interpretação" da aba de Tendências do Excel —
    duplicada em JS por necessidade (o navegador não roda Python), mas
    aqui só existe UMA implementação Python, não uma por consumidor.
    """
    if t is None:
        return "Histórico insuficiente."

    if t["significativo"] and t["direcao"] == "aumento":
        return f"Tendência de {rotulo_aumento} estatisticamente significativa (p={t['p_valor']:.3f})."
    if t["significativo"] and t["direcao"] == "reducao":
        return f"Tendência de {rotulo_reducao} estatisticamente significativa (p={t['p_valor']:.3f})."
    if estavel_quando_nao_significativo:
        return f"Estável — sem tendência estatisticamente significativa (p={t['p_valor']:.3f})."

    direcao_texto = rotulo_aumento if t["direcao"] == "aumento" else (rotulo_reducao if t["direcao"] == "reducao" else "estável")
    return f"Tendência de {direcao_texto}, NÃO estatisticamente significativa (p={t['p_valor']:.3f})."


def tendencia_mann_kendall(municipio):
    """Tendência de longo prazo da chuva ANUAL TOTAL — ver _tendencia_de_serie.
    Sobre climate.trends.totais_anuais. None se histórico curto demais."""
    municipio = _resolver_municipio(municipio)
    chave = _cache_key("tendencia_mann_kendall", municipio.codigo_ibge)

    def _calcular():
        anuais = trends.totais_anuais(municipio)
        if not anuais:
            return None
        anos = sorted(anuais)
        valores = [anuais[ano] for ano in anos]
        return _tendencia_de_serie(anos, valores)

    return _com_cache(chave, _calcular)


# =======================================================================
# Séries ANUAIS (1981→ano completo mais recente) — evolução ao longo do
# tempo dos indicadores de FASE 2, pra gráfico "ver evolução" na home
# (mesmo padrão sob demanda do spi_serie). Reaproveitam LIMIAR_DIA_SECO_MM/
# LIMIARES_DIA_CHUVOSO_MM já definidos acima e _tendencia_de_serie —
# nenhuma lógica de cálculo nova, só reagrupadas por ano em vez de um
# ano/período só.
# =======================================================================

def _registros_diarios_todos_anos(municipio):
    """
    dict {ano: [(data, valor), ...]} — TODOS os registros diários do
    município, uma query só, agrupados por ano civil COMPLETO (exclui o
    ano corrente, mesmo critério de totais_anuais). Ordenado por data
    dentro de cada ano (necessário pra veranico_maximo_serie_anual
    detectar sequência corretamente). Base compartilhada das 3 séries
    anuais abaixo — evita 45 queries por indicador.
    """
    ano_atual = timezone.localdate().year
    registros = (
        ChirpsData.objects.filter(municipio=municipio)
        .exclude(date__year=ano_atual)
        .order_by("date")
        .values_list("date", "value")
    )
    por_ano = {}
    for data, valor in registros:
        por_ano.setdefault(data.year, []).append((data, valor))
    return por_ano


def dias_chuvosos_serie_anual(municipio):
    """
    dict {"1": {"serie": {ano: n_dias}, "tendencia": {...} ou None},
    "5": {...}, "10": {...}} — os 3 limiares de LIMIARES_DIA_CHUVOSO_MM
    de uma vez (o card já permite alternar), cada um com sua própria
    tendência Mann-Kendall/Sen's slope (reaproveita _tendencia_de_serie
    — a tendência de "dias >5mm" é independente da de "dias >1mm", por
    isso uma por limiar, não uma só). None sem CHIRPS pro município.
    """
    municipio = _resolver_municipio(municipio)
    chave = _cache_key("dias_chuvosos_serie_anual", municipio.codigo_ibge)

    def _calcular():
        por_ano = _registros_diarios_todos_anos(municipio)
        if not por_ano:
            return None

        resultado = {}
        for limiar in LIMIARES_DIA_CHUVOSO_MM:
            serie = {
                ano: sum(1 for _data, valor in registros if valor > limiar)
                for ano, registros in por_ano.items()
            }
            anos = sorted(serie)
            valores = [serie[ano] for ano in anos]
            resultado[str(limiar)] = {"serie": serie, "tendencia": _tendencia_de_serie(anos, valores)}
        return resultado

    return _com_cache(chave, _calcular)


def intensidade_serie_anual(municipio):
    """
    {"serie": {ano: {total_mm, dias_com_chuva, intensidade_mm_por_dia_chuvoso}},
    "tendencia": {...} ou None} — evolução da intensidade ano a ano +
    Mann-Kendall/Sen's slope DESSA série especificamente (reaproveita
    _tendencia_de_serie — a tendência da intensidade é independente da
    tendência do total anual, por isso não reaproveita
    tendencia_mann_kendall, só o núcleo genérico). None sem CHIRPS.
    """
    municipio = _resolver_municipio(municipio)
    chave = _cache_key("intensidade_serie_anual", municipio.codigo_ibge)

    def _calcular():
        por_ano = _registros_diarios_todos_anos(municipio)
        if not por_ano:
            return None

        serie = {}
        for ano, registros in sorted(por_ano.items()):
            valores = [v for _data, v in registros]
            dias_com_chuva = [v for v in valores if v > LIMIAR_DIA_SECO_MM]
            serie[ano] = {
                "total_mm": round(sum(valores), 1),
                "dias_com_chuva": len(dias_com_chuva),
                "intensidade_mm_por_dia_chuvoso": (
                    round(sum(dias_com_chuva) / len(dias_com_chuva), 2) if dias_com_chuva else None
                ),
            }

        anos_com_intensidade = [ano for ano in sorted(serie) if serie[ano]["intensidade_mm_por_dia_chuvoso"] is not None]
        valores_intensidade = [serie[ano]["intensidade_mm_por_dia_chuvoso"] for ano in anos_com_intensidade]
        tendencia = _tendencia_de_serie(anos_com_intensidade, valores_intensidade)

        return {"serie": serie, "tendencia": tendencia}

    return _com_cache(chave, _calcular)


def veranico_maximo_serie_anual(municipio):
    """
    {"serie": {ano: {"dias","inicio","fim"} ou None}, "tendencia": {...}
    ou None} — maior sequência seca DENTRO de cada ano civil (a
    contagem reinicia em 1º de janeiro, mesmo critério calendário-
    fechado de dias_chuvosos/intensidade — um veranico que atravessasse
    dez/jan contaria pro ano em que cada trecho caiu, não pro ano
    todo), com Mann-Kendall/Sen's slope sobre o "dias" de cada ano
    (anos sem nenhum dia seco, teoricamente possível mas nunca visto em
    MT, ficam fora do cálculo de tendência). None sem CHIRPS.
    """
    municipio = _resolver_municipio(municipio)
    chave = _cache_key("veranico_maximo_serie_anual", municipio.codigo_ibge)

    def _calcular():
        por_ano = _registros_diarios_todos_anos(municipio)
        if not por_ano:
            return None

        serie = {ano: _maior_sequencia_em_lista(registros) for ano, registros in por_ano.items()}
        anos_com_valor = sorted(ano for ano in serie if serie[ano] is not None)
        valores = [serie[ano]["dias"] for ano in anos_com_valor]
        tendencia = _tendencia_de_serie(anos_com_valor, valores)

        return {"serie": serie, "tendencia": tendencia}

    return _com_cache(chave, _calcular)
