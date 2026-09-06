# climate/calculadora_exports.py
"""
Exportação .xlsx do resultado da calculadora de validação (ver
climate/calculadora_validacao.py) — 4 abas: Metadados, Métricas de
Validação, Dados Pareados (com colunas de acumulado, pro gráfico
"Acumulado Comparado" da calculadora) e Distribuição do Erro (as faixas
do histograma). Mesmo padrão de farms/exports.py e
climate/municipio_exports.py (Workbook + _nova_aba), openpyxl já
dependência do projeto.

Gerado em memória (BytesIO) e devolvido ao chamador — a view embute o
conteúdo como data URI na própria página de resultado (Opção A: zero
armazenamento no servidor, nem temporário — ver docs/DECISOES.md).
Este módulo não sabe nada sobre isso, só monta o workbook.
"""
from django.utils import timezone
from openpyxl import Workbook

from .municipio_exports import CITACAO_CHIRPS


def gerar_workbook_validacao(municipio, resultado):
    workbook = Workbook()
    workbook.remove(workbook.active)

    _aba_metadados(workbook, municipio, resultado)
    _aba_metricas(workbook, resultado)
    _aba_dados_pareados(workbook, resultado)
    _aba_distribuicao_erro(workbook, resultado)

    return workbook


def _nova_aba(workbook, titulo, cabecalho):
    aba = workbook.create_sheet(title=titulo)
    aba.append(cabecalho)
    return aba


def _aba_metadados(workbook, municipio, resultado):
    aba = _nova_aba(workbook, "Metadados", ["Campo", "Valor"])
    metricas = resultado["metricas"]

    aba.append(["Ferramenta", "Calculadora de Validação CHIRPS × Pluviômetro"])
    aba.append(["Município comparado", f"{municipio.nome}/{municipio.uf}"])
    aba.append(["Código IBGE", municipio.codigo_ibge])
    aba.append(["Granularidade detectada no arquivo enviado", resultado["granularidade"]])
    aba.append(["Nº de pares usados na validação", metricas["n_pares"] if metricas else 0])
    aba.append([
        "Amostra pequena (< 30 pares)",
        "Sim — resultado pode não ser estatisticamente representativo" if resultado["amostra_pequena"] else "Não",
    ])
    aba.append(["Data do cálculo", timezone.localtime().replace(tzinfo=None).strftime("%d/%m/%Y %H:%M")])
    aba.append(["Fonte do dado de comparação", "CHIRPS (Climate Hazards Group InfraRed Precipitation with Station data)"])
    aba.append(["Citação recomendada do CHIRPS", CITACAO_CHIRPS])


def _aba_metricas(workbook, resultado):
    aba = _nova_aba(workbook, "Métricas de Validação", ["Métrica", "Valor"])
    metricas = resultado["metricas"]
    if not metricas:
        aba.append(["Sem pares suficientes para calcular métricas", None])
        return

    aba.append(["Nº de pares (n)", metricas["n_pares"]])
    aba.append(["R²", round(metricas["r2"], 4)])
    aba.append(["RMSE (mm)", round(metricas["rmse"], 3)])
    aba.append(["MAE (mm)", round(metricas["mae"], 3)])
    aba.append(["MBE (mm) — viés médio", round(metricas["mbe"], 3)])
    aba.append(["Índice d (Willmott)", round(metricas["indice_d"], 4)])
    aba.append(["Índice c (Camargo-Sentelhas)", round(metricas["indice_c"], 4)])
    aba.append(["Desempenho (índice c)", metricas["desempenho_c"]])


def _aba_dados_pareados(workbook, resultado):
    # Acumulado CHIRPS/Medido: soma progressiva na mesma ordem cronológica
    # dos pares — sustenta o gráfico "Acumulado Comparado" da calculadora
    # pra quem quiser reproduzi-lo fora da ferramenta, sem recalcular nada.
    aba = _nova_aba(workbook, "Dados Pareados", [
        "Data", "CHIRPS (mm)", "Medido (mm)", "Diferença (CHIRPS - medido)",
        "CHIRPS Acumulado (mm)", "Medido Acumulado (mm)",
    ])
    acumulado_chirps = 0.0
    acumulado_local = 0.0
    for data, chirps, local in resultado["pares"]:
        acumulado_chirps += chirps
        acumulado_local += local
        aba.append([
            data, round(chirps, 2), round(local, 2), round(chirps - local, 2),
            round(acumulado_chirps, 2), round(acumulado_local, 2),
        ])


def _fmt2(valor):
    """Duas casas decimais, mas nunca "-0.00" (valor real ligeiramente
    negativo que arredonda pra zero) — só cosmético, mesmo cuidado de
    climate/calculadora_narrativas.py:_fmt1."""
    texto = f"{valor:.2f}"
    return "0.00" if texto == "-0.00" else texto


def _aba_distribuicao_erro(workbook, resultado):
    aba = _nova_aba(workbook, "Distribuição do Erro", ["Faixa (mm)", "Contagem"])
    for faixa in resultado.get("histograma") or []:
        aba.append([f"{_fmt2(faixa['inicio'])} a {_fmt2(faixa['fim'])}", faixa["contagem"]])
