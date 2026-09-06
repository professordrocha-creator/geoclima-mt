# climate/calculadora_narrativas.py
"""
Texto de interpretação (conceito fixo no frontend + leitura dinâmica dos
dados aqui) pros 6 gráficos da Calculadora de Validação CHIRPS ×
Pluviômetro — mesmo espírito de climate/municipio_narrativas.py (Home
pública): DESCREVE o que o arquivo enviado pelo usuário mostra, nunca
PRESCREVE ("descarte esses dados") nem PREVÊ. Recebe sempre o
`resultado` já calculado por climate.calculadora_validacao.calcular_
validacao — nenhum cálculo novo aqui além de composição de frase
(a correlação do Erro × Magnitude é a única conta nova, reaproveitando
statistics.correlation do mesmo jeito que climate/validation.py já
faz).
"""
import statistics

from .municipio_narrativas import _MESES_NOME

_ROTULO_DESEMPENHO_C = {
    "otimo": "ótima",
    "muito_bom": "muito boa",
    "bom": "boa",
    "mediano": "mediana",
    "sofrivel": "sofrível",
    "mau": "fraca",
    "pessimo": "muito fraca",
}


def _fmt1(valor):
    """Uma casa decimal, mas nunca "-0.0" (valor real ligeiramente
    negativo que arredonda pra zero) — só cosmético, o cálculo em si
    continua usando o valor original, sem arredondar antes da hora."""
    texto = f"{valor:.1f}"
    return "0.0" if texto == "-0.0" else texto


def _rotulo_data(data, granularidade):
    if granularidade == "mensal":
        return f"{_MESES_NOME[data.month - 1]}/{data.year}"
    return data.strftime("%d/%m/%Y")


def interpretar_dispersao(metricas):
    """Traduz o índice c (nome técnico) pra uma leitura em uma frase —
    R²/índice c já aparecem nos cards de métrica, isso só dá contexto
    de leitura ao gráfico."""
    if metricas is None:
        return None
    rotulo = _ROTULO_DESEMPENHO_C.get(metricas["desempenho_c"], metricas["desempenho_c"])
    return (
        f"O índice c (Camargo-Sentelhas) de {metricas['indice_c']:.2f} indica concordância {rotulo} entre as "
        f"duas fontes — quanto mais os pontos se aproximam da linha diagonal tracejada, mais o CHIRPS e o "
        f"pluviômetro concordam neste conjunto de dados. O R² de {metricas['r2']:.2f} mostra que "
        f"{metricas['r2'] * 100:.0f}% da variação do dado medido acompanha a variação do CHIRPS."
    )


def interpretar_serie_temporal(pares, granularidade):
    """Aponta o período de maior divergência isolada entre as duas
    séries — o gráfico já mostra visualmente onde elas se afastam, a
    frase só nomeia o ponto mais extremo."""
    if not pares:
        return None
    data, chirps, local = max(pares, key=lambda p: abs(p[1] - p[2]))
    diferenca = chirps - local
    return (
        f"A maior divergência isolada entre as duas séries foi em {_rotulo_data(data, granularidade)}: o CHIRPS "
        f"registrou {chirps:.1f} mm contra {local:.1f} mm medidos no pluviômetro (diferença de {diferenca:+.1f} mm)."
    )


def interpretar_residuos(pares, metricas):
    """Proporção de superestimativa vs. subestimativa — o MBE já resume
    isso numa média, mas não diz se ela vem de um padrão consistente
    (maioria dos pontos do mesmo lado de zero) ou de poucos valores
    extremos puxando a média."""
    if not pares or metricas is None:
        return None
    diferencas = [chirps - local for _data, chirps, local in pares]
    n = len(diferencas)
    positivos = sum(1 for d in diferencas if d > 0)
    negativos = sum(1 for d in diferencas if d < 0)
    empatados = n - positivos - negativos

    if metricas["mbe"] > 0:
        sinal_mbe = "superestimou"
    elif metricas["mbe"] < 0:
        sinal_mbe = "subestimou"
    else:
        sinal_mbe = "não teve viés médio"

    partes = [
        f"Em {positivos} de {n} períodos ({positivos / n * 100:.0f}%) o CHIRPS superestimou a chuva medida; "
        f"em {negativos} ({negativos / n * 100:.0f}%), subestimou"
    ]
    if empatados:
        partes.append(f"; em {empatados}, os valores coincidiram exatamente")
    partes.append(f". Na média (MBE), o CHIRPS {sinal_mbe} neste conjunto de dados.")
    return "".join(partes)


def interpretar_acumulado(pares, metricas):
    """Compara a soma dos erros absolutos de cada período (que dá
    origem ao MAE) com a diferença do total acumulado no fim do
    período — se o acumulado final for bem menor que essa soma, os
    erros se compensam (superestima num período, subestima em outro);
    se for parecido, o erro é sistemático (sempre na mesma direção)."""
    if not pares or metricas is None:
        return None
    acumulado_chirps = sum(chirps for _d, chirps, _l in pares)
    acumulado_local = sum(local for _d, _c, local in pares)
    diferenca_acumulada = acumulado_chirps - acumulado_local
    soma_erros_absolutos = sum(abs(chirps - local) for _d, chirps, local in pares)
    pct_final = (diferenca_acumulada / acumulado_local * 100) if acumulado_local else 0.0

    if soma_erros_absolutos > 0 and abs(diferenca_acumulada) < soma_erros_absolutos * 0.5:
        leitura = (
            " Boa parte dos erros de cada período se compensa no acumulado — quando o CHIRPS superestima em um "
            "período, tende a subestimar em outro, reduzindo a diferença total."
        )
    else:
        leitura = (
            " Os erros de cada período tendem a apontar na mesma direção — por isso a diferença não se reduz "
            "no acumulado, e sim se soma."
        )

    return (
        f"Ao final do período, o total acumulado do CHIRPS foi {acumulado_chirps:.0f} mm contra "
        f"{acumulado_local:.0f} mm medidos no pluviômetro — uma diferença de {diferenca_acumulada:+.0f} mm "
        f"({pct_final:+.0f}% do total medido)." + leitura
    )


def interpretar_histograma(histograma, metricas):
    """Aponta a faixa (bin) com mais ocorrências e se ela está perto de
    zero (erro tipicamente pequeno) ou deslocada (viés predominante
    numa direção) — a forma da distribuição, que RMSE/MAE (só um
    número) não mostram."""
    if not histograma or metricas is None:
        return None
    faixa_mais_frequente = max(histograma, key=lambda f: f["contagem"])
    n = sum(f["contagem"] for f in histograma)
    if n == 0:
        return None
    pct = faixa_mais_frequente["contagem"] / n * 100

    if faixa_mais_frequente["inicio"] <= 0 <= faixa_mais_frequente["fim"]:
        leitura_posicao = "próxima de zero, ou seja, o erro mais comum neste conjunto de dados é pequeno"
    elif faixa_mais_frequente["inicio"] > 0:
        leitura_posicao = "deslocada para valores positivos, ou seja, o CHIRPS costuma superestimar neste conjunto de dados"
    else:
        leitura_posicao = "deslocada para valores negativos, ou seja, o CHIRPS costuma subestimar neste conjunto de dados"

    return (
        f"A faixa de erro mais frequente foi entre {_fmt1(faixa_mais_frequente['inicio'])} e "
        f"{_fmt1(faixa_mais_frequente['fim'])} mm ({faixa_mais_frequente['contagem']} de {n} pares, {pct:.0f}%) — "
        f"{leitura_posicao}."
    )


def interpretar_erro_magnitude(pares):
    """Correlação entre o valor MEDIDO (referência) e o tamanho do erro
    (CHIRPS - medido) — não confundir com a correlação CHIRPS×medido
    já mostrada no gráfico de dispersão (esta é sobre o ERRO, não sobre
    a concordância bruta). Um padrão aqui (erro cresce ou diminui com
    a chuva medida) é o que a literatura chama de viés condicional: a
    precisão do CHIRPS muda dependendo de quanto choveu, em vez de ser
    constante — um comportamento conhecido de produtos de satélite
    (tendência a subestimar eventos de chuva muito intensa)."""
    if len(pares) < 3:
        return None
    valores_locais = [local for _d, _c, local in pares]
    diferencas = [chirps - local for _d, chirps, local in pares]
    if statistics.pstdev(valores_locais) == 0 or statistics.pstdev(diferencas) == 0:
        return (
            "Não foi possível avaliar um padrão entre o tamanho do erro e a intensidade da chuva medida "
            "(valores constantes neste conjunto de dados)."
        )

    r = statistics.correlation(valores_locais, diferencas)

    if abs(r) < 0.3:
        return (
            f"A correlação entre a chuva medida e o tamanho do erro é fraca (r={r:.2f}) — não há um padrão claro "
            "de que o erro do CHIRPS cresça ou diminua conforme a chuva medida aumenta neste conjunto de dados."
        )

    direcao = (
        "o CHIRPS tende a superestimar cada vez mais conforme a chuva medida aumenta"
        if r > 0 else
        "o CHIRPS tende a subestimar cada vez mais conforme a chuva medida aumenta"
    )
    intensidade_r = "forte" if abs(r) >= 0.5 else "moderada"
    return (
        f"Há uma correlação {intensidade_r} (r={r:.2f}) entre a chuva medida e o tamanho do erro: {direcao}. Isso "
        "é chamado de viés condicional — quando a precisão de uma fonte muda dependendo da intensidade do evento, "
        "em vez de ser constante em qualquer volume de chuva."
    )


def gerar_interpretacoes(resultado):
    """Dict com as 6 chaves usadas pelo template (dispersao,
    serieTemporal, residuos, acumulado, histograma, erroMagnitude) —
    cada função se protege sozinha (retorna None) quando não há dado
    suficiente pra gerar a leitura."""
    pares = resultado["pares"]
    metricas = resultado["metricas"]
    granularidade = resultado["granularidade"]
    histograma = resultado.get("histograma")

    return {
        "dispersao": interpretar_dispersao(metricas),
        "serieTemporal": interpretar_serie_temporal(pares, granularidade),
        "residuos": interpretar_residuos(pares, metricas),
        "acumulado": interpretar_acumulado(pares, metricas),
        "histograma": interpretar_histograma(histograma, metricas),
        "erroMagnitude": interpretar_erro_magnitude(pares),
    }
