# climate/municipio_narrativas.py
"""
Texto de interpretação (não só o conceito fixo) pros gráficos da home
pública — PROTÓTIPO em avaliação, aguardando validação de tom antes de
ligar nos endpoints/frontend (ver docs/HISTORICO.md).

Mesmo espírito de dashboard/insights.py (Etapa 9.2, painel privado, NÃO
tocado por este módulo): DESCREVE o que os dados mostram, nunca PREVÊ
("vai piorar") nem PRESCREVE ação ("irrigue agora"). Reaproveita
climate.municipio_indicators.interpretar_tendencia (já existe, já usada
na aba de Tendências do Excel) como núcleo da frase de significância —
este módulo só adiciona a frase de esclarecimento em linguagem simples
e os achados descritivos que não têm função pronta ainda (maior seca já
registrada, mês mais chuvoso, etc.).

Todas as funções recebem dados JÁ CALCULADOS (séries/dicionários que
climate.municipio_indicators já produz) — nenhum cálculo novo aqui, só
composição de frase.
"""
from spi.models import SpiResult

from . import municipio_indicators as mi

_CLASSIFICACAO_LABEL = dict(SpiResult.CLASSIFICATIONS)

_MESES_NOME = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
    "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def _mes_ano(data):
    return f"{_MESES_NOME[data.month - 1]}/{data.year}"


def interpretar_spi_serie(serie, escala):
    """
    Descreve a série COMPLETA de SPI-`escala` de um município (todo o
    histórico importado, não só o período que o usuário escolheu ver
    no gráfico — o filtro de 5/10 anos/tudo é só de exibição no
    frontend; a interpretação sempre descreve o histórico completo,
    pra não mudar de leitura dependendo do zoom escolhido): condição
    atual, episódio mais seco e mais úmido já registrados. None se a
    série estiver vazia (histórico insuficiente).
    """
    if not serie:
        return None

    atual = serie[-1]
    mais_seco = min(serie, key=lambda p: p["value"])
    mais_umido = max(serie, key=lambda p: p["value"])

    label_atual = _CLASSIFICACAO_LABEL.get(atual["classification"], atual["classification"])
    label_seco = _CLASSIFICACAO_LABEL.get(mais_seco["classification"], mais_seco["classification"])
    label_umido = _CLASSIFICACAO_LABEL.get(mais_umido["classification"], mais_umido["classification"])

    return (
        f"O valor mais recente de SPI-{escala} é {atual['value']:.2f} ({label_atual.lower()}). "
        f"No histórico completo (desde {serie[0]['date'].year}), o momento mais seco foi em "
        f"{_mes_ano(mais_seco['date'])}, com SPI-{escala} de {mais_seco['value']:.2f} ({label_seco.lower()}); "
        f"o mais chuvoso foi em {_mes_ano(mais_umido['date'])}, "
        f"com {mais_umido['value']:.2f} ({label_umido.lower()})."
    )


def interpretar_spi_todas_escalas(spi_por_escala):
    """
    Compara o SPI atual nas 4 escalas (mesmo dict já devolvido por
    /api/municipios/<id>/indicadores/) — cita os 4 valores e destaca se
    o curto prazo (SPI-1) e o longo prazo (SPI-12) mostram a mesma
    condição ou condições diferentes (escalas curtas reagem primeiro a
    mudanças na chuva, então divergência entre elas já é informativa
    por si só, sem precisar prever nada). None se nenhuma escala tiver
    valor.
    """
    partes = []
    for escala in ("1", "3", "6", "12"):
        dado = spi_por_escala.get(escala)
        if dado and dado.get("value") is not None:
            label = _CLASSIFICACAO_LABEL.get(dado["classification"], dado["classification"])
            partes.append(f"SPI-{escala} = {dado['value']:.2f} ({label.lower()})")

    if not partes:
        return None
    resumo_valores = "; ".join(partes)

    curto = spi_por_escala.get("1")
    longo = spi_por_escala.get("12")
    if curto and longo and curto.get("classification") and longo.get("classification"):
        if curto["classification"] == longo["classification"]:
            comparacao = " O curto prazo (SPI-1) e o longo prazo (SPI-12) mostram a mesma condição atual."
        else:
            label_curto = _CLASSIFICACAO_LABEL.get(curto["classification"], curto["classification"])
            label_longo = _CLASSIFICACAO_LABEL.get(longo["classification"], longo["classification"])
            comparacao = (
                f" O curto prazo (SPI-1) está em {label_curto.lower()}, "
                f"enquanto o longo prazo (SPI-12) está em {label_longo.lower()} — "
                f"escalas mais curtas costumam reagir primeiro a mudanças na chuva."
            )
    else:
        comparacao = ""

    return f"Valores atuais: {resumo_valores}.{comparacao}"


def interpretar_climatologia(climatologia):
    """Identifica o(s) mês(es) mais chuvoso(s) e mais seco(s) da climatologia
    mensal (dict {mes: {media, ...}} de municipio_indicators.climatologia_mensal).
    None se vier vazio."""
    if not climatologia:
        return None

    mes_mais_chuvoso = max(climatologia, key=lambda m: climatologia[m]["media"])
    mes_mais_seco = min(climatologia, key=lambda m: climatologia[m]["media"])

    return (
        f"O mês historicamente mais chuvoso é {_MESES_NOME[mes_mais_chuvoso - 1]} "
        f"(média de {climatologia[mes_mais_chuvoso]['media']:.0f} mm); "
        f"o mais seco é {_MESES_NOME[mes_mais_seco - 1]} "
        f"(média de {climatologia[mes_mais_seco]['media']:.0f} mm)."
    )


def interpretar_climatologia_ano(climatologia, totais_mensais_ano, ano):
    """
    Compara os totais mensais de UM ano escolhido contra a faixa normal
    histórica (P25–P75) de cada mês — conta quantos meses do ano ficaram
    abaixo da faixa (< P25), acima (> P75), ou dentro dela, e destaca o
    mês de MAIOR desvio absoluto em relação à mediana histórica. Só
    descreve o que os dados JÁ mostram (nunca "vai chover"/"deve chover")
    — é o gráfico de climatologia com ano sobreposto, apoio à decisão
    sem previsão.

    `totais_mensais_ano`: dict {mes (1-12): valor_mm} — mês sem dado
    nesse ano simplesmente não entra na contagem. None se nenhum mês do
    ano tiver climatologia E dado disponíveis ao mesmo tempo.
    """
    abaixo, acima, dentro = 0, 0, 0
    maior_desvio = None  # (mes, desvio_absoluto, valor, normal_do_mes)

    for mes in range(1, 13):
        valor = totais_mensais_ano.get(mes)
        normal = climatologia.get(mes)
        if valor is None or normal is None:
            continue

        if valor < normal["p25"]:
            abaixo += 1
        elif valor > normal["p75"]:
            acima += 1
        else:
            dentro += 1

        desvio = abs(valor - normal["mediana"])
        if maior_desvio is None or desvio > maior_desvio[1]:
            maior_desvio = (mes, desvio, valor, normal)

    total_meses_com_dado = abaixo + acima + dentro
    if total_meses_com_dado == 0:
        return None

    def _ficar(n):
        return "ficou" if n == 1 else "ficaram"

    partes = [
        f"Em {ano}, dos {total_meses_com_dado} meses com dado disponível: "
        f"{abaixo} {_ficar(abaixo)} abaixo da faixa histórica normal (< P25), "
        f"{acima} {_ficar(acima)} acima (> P75), e {dentro} dentro da faixa normal."
    ]

    if maior_desvio:
        mes, _desvio, valor, normal = maior_desvio
        partes.append(
            f"O mês com maior desvio foi {_MESES_NOME[mes - 1]}, com {valor:.0f} mm "
            f"— a mediana histórica para {_MESES_NOME[mes - 1]} é {normal['mediana']:.0f} mm "
            f"(faixa normal: {normal['p25']:.0f}–{normal['p75']:.0f} mm)."
        )

    return " ".join(partes)


def interpretar_tendencia_narrativa(tendencia, rotulo_aumento, rotulo_reducao):
    """
    Envolve mi.interpretar_tendencia (já existe, já usada na aba de
    Tendências do Excel) com uma frase extra em linguagem simples
    explicando o que "significativo"/"não significativo" quer dizer —
    a parte que um leigo não decodifica só pelo p-valor. None se
    `tendencia` for None (histórico insuficiente).
    """
    if tendencia is None:
        return None

    frase_tecnica = mi.interpretar_tendencia(tendencia, rotulo_aumento, rotulo_reducao, estavel_quando_nao_significativo=False)

    if tendencia["significativo"]:
        esclarecimento = "Isso significa que a mudança é consistente ao longo do tempo, não apenas uma variação ocasional de um ano para outro."
    else:
        esclarecimento = "Isso significa que a variação observada pode ser apenas oscilação natural de um ano para outro, sem um padrão confiável de mudança."

    return f"{frase_tecnica} {esclarecimento}"


def interpretar_assinatura(tendencia_dias_chuvosos, tendencia_intensidade):
    """
    Compara a tendência de frequência (dias chuvosos) com a de
    intensidade — a leitura "chove menos vezes, mas mais forte" (ou o
    oposto, ou nenhuma das duas) só faz sentido olhando as duas juntas.
    A síntese final só aparece nas combinações em que há algo específico
    e sustentado pelos dois testes pra dizer (frequência muda de forma
    significativa E intensidade some claramente estável ou na direção
    oposta) — fora disso, fica só a descrição de cada uma, sem forçar
    uma frase genérica. None se as duas tendências forem None.
    """
    if tendencia_dias_chuvosos is None and tendencia_intensidade is None:
        return None

    def _resumo(t, rotulo_aumento, rotulo_reducao):
        if t is None:
            return None, "sem histórico suficiente pra avaliar"
        if not t["significativo"]:
            return "estavel", f"estável (sem tendência estatisticamente significativa, p={t['p_valor']:.3f})"
        return t["direcao"], (rotulo_aumento if t["direcao"] == "aumento" else rotulo_reducao)

    direcao_dias, texto_dias = _resumo(tendencia_dias_chuvosos, "aumentando de forma significativa", "diminuindo de forma significativa")
    direcao_intensidade, texto_intensidade = _resumo(tendencia_intensidade, "aumentando de forma significativa", "diminuindo de forma significativa")

    base = f"Dias de chuva: {texto_dias}. Intensidade por dia chuvoso: {texto_intensidade}."

    sinteses = {
        ("reducao", "estavel"): " Ou seja: chove em menos dias, mas a força de cada chuva não mudou de forma significativa.",
        ("reducao", "aumento"): " Ou seja: chove em menos dias, e quando chove, a chuva tende a ser mais forte.",
        ("aumento", "estavel"): " Ou seja: chove em mais dias, mas a força de cada chuva não mudou de forma significativa.",
        ("aumento", "reducao"): " Ou seja: chove em mais dias, e quando chove, a chuva tende a ser mais fraca.",
    }
    sintese = sinteses.get((direcao_dias, direcao_intensidade), "")

    return base + sintese
