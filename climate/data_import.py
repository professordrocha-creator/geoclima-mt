# climate/data_import.py
"""
Importação de arquivo (.csv ou .xlsx) de precipitação manual/de estação
(Etapa 6). Detecta colunas pelo NOME do cabeçalho (case-insensitive,
aceita variações comuns em português/inglês) — não exige um template
rígido de planilha, já que cada produtor exporta os dados do jeito que
o pluviômetro/estação dele já fornece.

Colunas obrigatórias: data e valor (chuva em mm).
Colunas opcionais: horário, observações.
"""
import csv
import io
from datetime import datetime

import openpyxl

COLUNAS_DATA = ["data", "date"]
COLUNAS_VALOR = ["valor", "chuva", "precipitacao", "precipitação", "mm", "value"]
COLUNAS_HORARIO = ["horario", "horário", "hora", "time"]
COLUNAS_OBSERVACOES = ["observacoes", "observações", "obs", "notes", "notas"]

FORMATOS_DATA = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]
FORMATOS_HORA = ["%H:%M:%S", "%H:%M"]


class ErroImportacao(Exception):
    """Erro que impede a importação inteira (arquivo ilegível, sem colunas obrigatórias etc.)."""


def processar_arquivo(arquivo_upload):
    """
    Retorna (registros, erros_de_linha).
    registros: lista de dicts {"date": date, "value": float, "time": time|None, "notes": str}
    erros_de_linha: lista de strings (linhas individuais que não deu pra interpretar,
    não impedem as outras linhas de serem importadas).
    """
    nome = arquivo_upload.name.lower()
    if nome.endswith(".csv"):
        linhas = _ler_csv(arquivo_upload)
    elif nome.endswith(".xlsx"):
        linhas = _ler_xlsx(arquivo_upload)
    else:
        raise ErroImportacao("Formato não suportado. Envie um arquivo .csv ou .xlsx.")

    linhas = [linha for linha in linhas if any(str(celula).strip() for celula in linha)]
    if not linhas:
        raise ErroImportacao("Arquivo vazio ou sem linhas de dados.")

    cabecalho = [str(c).strip().lower() for c in linhas[0]]
    indice_data = _achar_coluna(cabecalho, COLUNAS_DATA)
    indice_valor = _achar_coluna(cabecalho, COLUNAS_VALOR)
    indice_horario = _achar_coluna(cabecalho, COLUNAS_HORARIO)
    indice_obs = _achar_coluna(cabecalho, COLUNAS_OBSERVACOES)

    if indice_data is None or indice_valor is None:
        raise ErroImportacao(
            f"Não encontrei colunas de data e valor no cabeçalho ({', '.join(cabecalho)}). "
            "Use um cabeçalho com 'data'/'date' e 'valor'/'chuva'/'precipitacao'."
        )

    registros = []
    erros = []
    for numero_linha, linha in enumerate(linhas[1:], start=2):
        try:
            data = _parsear_data(linha[indice_data])
            valor = float(str(linha[indice_valor]).replace(",", "."))
            horario = None
            if indice_horario is not None and indice_horario < len(linha) and linha[indice_horario]:
                horario = _parsear_hora(linha[indice_horario])
            observacoes = ""
            if indice_obs is not None and indice_obs < len(linha) and linha[indice_obs]:
                observacoes = str(linha[indice_obs]).strip()
            registros.append({"date": data, "value": valor, "time": horario, "notes": observacoes})
        except (ValueError, IndexError) as exc:
            erros.append(f"Linha {numero_linha}: {exc}")

    return registros, erros


def _achar_coluna(cabecalho, candidatos):
    for indice, nome_coluna in enumerate(cabecalho):
        if nome_coluna in candidatos:
            return indice
    return None


def _ler_csv(arquivo_upload):
    conteudo = arquivo_upload.read().decode("utf-8-sig")
    try:
        dialeto = csv.Sniffer().sniff(conteudo[:2048], delimiters=",;")
    except csv.Error:
        dialeto = csv.excel  # separador padrão (vírgula) se não conseguir detectar
    leitor = csv.reader(io.StringIO(conteudo), dialeto)
    return list(leitor)


def _ler_xlsx(arquivo_upload):
    planilha = openpyxl.load_workbook(arquivo_upload, data_only=True).active
    return [list(linha) for linha in planilha.iter_rows(values_only=True)]


def _parsear_data(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if hasattr(valor, "year") and hasattr(valor, "month"):  # datetime.date (Excel já converte)
        return valor
    texto = str(valor).strip()
    for formato in FORMATOS_DATA:
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    raise ValueError(f"data '{texto}' não reconhecida (use AAAA-MM-DD ou DD/MM/AAAA)")


def _parsear_hora(valor):
    if hasattr(valor, "hour"):  # datetime.time (Excel já converte)
        return valor
    texto = str(valor).strip()
    for formato in FORMATOS_HORA:
        try:
            return datetime.strptime(texto, formato).time()
        except ValueError:
            continue
    raise ValueError(f"horário '{texto}' não reconhecido (use HH:MM)")
