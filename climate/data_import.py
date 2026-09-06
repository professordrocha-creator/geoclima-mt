# climate/data_import.py
"""
Importação de arquivo (.csv ou .xlsx) de precipitação manual/de estação
(Etapa 6, reaproveitado também pela Calculadora de Validação pública) —
não exige um template rígido de planilha, já que cada
produtor/pesquisador exporta os dados do jeito que o pluviômetro/
estação dele já fornece.

Colunas obrigatórias: data e valor (chuva em mm).
Colunas opcionais: horário, observações.

DETECÇÃO DE COLUNA: por RADICAL, não por lista fechada de nomes exatos
— cada cabeçalho é normalizado (minúsculo, sem acento, sem espaço/
underscore/parênteses/hífen: "Chuva (mm)" e "chuva_mm" viram a mesma
chave "chuvamm") e comparado contra um conjunto de radicais conhecidos.
Isso aceita variações que um nome fixo não cobriria ("chuva_mm",
"PRECIPITAÇÃO_MM", "rainfall_mm", "data_medicao") sem precisar listar
cada combinação de maiúscula/underscore/unidade que alguém possa usar.
Achado real (usuário testou com "chuva_mm" e o sistema recusou —
motivou esta correção).

Cuidado deliberado: "prec" sozinho NÃO entra na lista de radicais de
valor (ficaria "precip" só) — bateria também em "preço" e "precisão"
(ambos contêm "prec" depois de normalizados), colunas que não têm nada
a ver com chuva.
"""
import csv
import io
import re
import unicodedata
from datetime import datetime

import openpyxl

# Radicais — string PRECISA CONTER um destes (não precisa ser igual).
RADICAIS_DATA = ["data", "date", "dia"]
RADICAIS_VALOR = ["chuv", "precip", "pluv", "rain", "ppt", "mm", "valor", "value"]
RADICAIS_HORARIO = ["horari", "hora", "time"]
RADICAIS_OBSERVACOES = ["observac", "obs", "notes", "nota"]

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

    cabecalho_original = [str(c).strip() for c in linhas[0]]
    cabecalho_normalizado = [_normalizar_nome_coluna(c) for c in cabecalho_original]

    # Ordem importa: data e valor primeiro (obrigatórios, prioridade) —
    # cada achado exclui esse índice das buscas seguintes, evitando a
    # mesma coluna sendo reclamada por dois papéis diferentes.
    indice_data = _achar_coluna(cabecalho_normalizado, RADICAIS_DATA)
    usados = {indice_data} if indice_data is not None else set()

    indice_valor = _achar_coluna(cabecalho_normalizado, RADICAIS_VALOR, excluir=usados)
    if indice_valor is not None:
        usados.add(indice_valor)

    indice_horario = _achar_coluna(cabecalho_normalizado, RADICAIS_HORARIO, excluir=usados)
    if indice_horario is not None:
        usados.add(indice_horario)

    indice_obs = _achar_coluna(cabecalho_normalizado, RADICAIS_OBSERVACOES, excluir=usados)

    if indice_data is None or indice_valor is None:
        faltando = []
        if indice_data is None:
            faltando.append("data (aceita, por ex.: 'data', 'date', 'dia', 'data_medicao')")
        if indice_valor is None:
            faltando.append(
                "valor de chuva (aceita, por ex.: 'valor', 'chuva', 'chuva_mm', 'precipitacao', "
                "'pluviometria', 'rainfall_mm')"
            )
        raise ErroImportacao(
            f"Não encontrei coluna de {' e de '.join(faltando)} no cabeçalho deste arquivo. "
            f"Colunas encontradas no arquivo: {', '.join(cabecalho_original)}. "
            "Renomeie a coluna correspondente pra um nome parecido com os aceitos e tente de novo."
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


def _normalizar_nome_coluna(nome):
    """minúsculo, sem acento, só letras/números — 'Chuva (mm)', 'chuva_mm'
    e 'CHUVA-MM' viram a mesma chave 'chuvamm'."""
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]", "", sem_acento.lower())


def _achar_coluna(cabecalho_normalizado, radicais, excluir=None):
    """Primeiro índice cujo nome normalizado CONTÉM algum dos radicais —
    não precisa ser igual (aceita 'chuva_mm', 'precipitacaomm' etc.).
    `excluir` pula índices já reclamados por outro papel de coluna."""
    excluir = excluir or set()
    for indice, nome in enumerate(cabecalho_normalizado):
        if indice in excluir:
            continue
        if any(radical in nome for radical in radicais):
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
