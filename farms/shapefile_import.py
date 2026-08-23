# farms/shapefile_import.py
"""
Importação de shapefile no cadastro de fazenda (Etapa 5).

Recebe um .zip enviado pelo usuário (padrão .shp + .shx + .dbf + .prj
juntos, igual ao formato do IBGE já usado em
maps/management/commands/import_municipios.py), extrai pra uma pasta
temporária, e lê TODOS os .shp encontrados dentro (em qualquer
subpasta) via GDAL:

- Feições de polígono/multipolígono de todos os arquivos viram UM
  MultiPolygon só (união de tudo), reprojetado pra WGS84 (SRID 4326) —
  vira o contorno da fazenda (Farm.poligono).
- Feições de ponto/multiponto viram uma lista de estações a criar, cada
  uma com nome lido de uma coluna de atributo do shapefile (se existir
  alguma parecida com "nome"/"name") ou um nome genérico.

Se o .prj não existir num shapefile, o GDAL não sabe a projeção de
origem — nesse caso assumimos que as coordenadas já estão em WGS84 (não
reprojeta) e avisamos no retorno, já que não tem como ter certeza.
"""
import os
import tempfile
import zipfile

from django.contrib.gis.gdal import DataSource
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon, Point

# Colunas de atributo candidatas a "nome da estação", em ordem de preferência.
CAMPOS_NOME_CANDIDATOS = ["nome", "name", "NOME", "NAME", "estacao", "ESTACAO", "rotulo", "label", "LABEL"]


class ResultadoImportacaoShapefile:
    def __init__(self):
        self.poligono = None  # MultiPolygon ou None
        self.pontos = []  # lista de dicts: {"nome": str, "latitude": float, "longitude": float}
        self.avisos = []  # mensagens não-fatais (ex.: shapefile sem .prj)


def processar_shapefile_zip(arquivo_upload):
    """
    arquivo_upload: um UploadedFile do Django (request.FILES['shapefile']).
    Retorna um ResultadoImportacaoShapefile. Levanta ValueError se o zip
    não tiver nenhum .shp válido dentro.
    """
    resultado = ResultadoImportacaoShapefile()

    with tempfile.TemporaryDirectory(prefix="geoclima_shp_") as pasta_temp:
        caminho_zip = os.path.join(pasta_temp, "upload.zip")
        with open(caminho_zip, "wb") as destino:
            for pedaco in arquivo_upload.chunks():
                destino.write(pedaco)

        try:
            with zipfile.ZipFile(caminho_zip) as zip_arquivo:
                zip_arquivo.extractall(pasta_temp)
        except zipfile.BadZipFile:
            raise ValueError("O arquivo enviado não é um .zip válido.")

        caminhos_shp = []
        for raiz, _dirs, arquivos in os.walk(pasta_temp):
            for nome_arquivo in arquivos:
                if nome_arquivo.lower().endswith(".shp"):
                    caminhos_shp.append(os.path.join(raiz, nome_arquivo))

        if not caminhos_shp:
            raise ValueError("Nenhum arquivo .shp encontrado dentro do .zip enviado.")

        poligonos_encontrados = []

        for caminho_shp in sorted(caminhos_shp):
            try:
                datasource = DataSource(caminho_shp)
            except Exception as exc:
                resultado.avisos.append(f"Não consegui abrir {os.path.basename(caminho_shp)}: {exc}")
                continue

            camada = datasource[0]
            tem_prj = os.path.exists(caminho_shp[:-4] + ".prj")
            if not tem_prj:
                resultado.avisos.append(
                    f"{os.path.basename(caminho_shp)} não tem arquivo .prj — assumindo que já está em WGS84 "
                    "(coordenadas podem ficar erradas se a origem for outra)."
                )

            nome_geom = (camada.geom_type.name or "").lower()

            if "polygon" in nome_geom:
                for feicao in camada:
                    geom_geos = _extrair_geometria_wgs84(feicao, tem_prj)
                    if geom_geos.geom_type == "Polygon":
                        geom_geos = MultiPolygon(geom_geos, srid=4326)
                    poligonos_encontrados.append(geom_geos)

            elif "point" in nome_geom:
                for indice, feicao in enumerate(camada, start=1):
                    geom_geos = _extrair_geometria_wgs84(feicao, tem_prj)
                    # MultiPoint com 1 ponto ainda conta como 1 estação; se
                    # tiver mais de um ponto na mesma feição, cada um vira
                    # uma estação separada.
                    pontos_da_feicao = geom_geos if geom_geos.geom_type == "MultiPoint" else [geom_geos]
                    for ponto in pontos_da_feicao:
                        nome = _extrair_nome(feicao, indice)
                        resultado.pontos.append({
                            "nome": nome,
                            "latitude": ponto.y,
                            "longitude": ponto.x,
                        })
            else:
                resultado.avisos.append(
                    f"{os.path.basename(caminho_shp)} tem geometria do tipo '{camada.geom_type.name}' "
                    "— ignorado (só polígono vira contorno e ponto vira estação)."
                )

        if poligonos_encontrados:
            unido = poligonos_encontrados[0]
            for geom in poligonos_encontrados[1:]:
                unido = unido.union(geom)
            resultado.poligono = unido if unido.geom_type == "MultiPolygon" else MultiPolygon(unido, srid=4326)
            resultado.poligono.srid = 4326

    return resultado


def _extrair_geometria_wgs84(feicao, tem_prj):
    """Converte a geometria de uma feição do GDAL pra GEOSGeometry em SRID 4326."""
    geom_gdal = feicao.geom
    if tem_prj:
        geom_gdal.transform(4326)
    geos_geom = GEOSGeometry(geom_gdal.wkb, srid=4326)
    return geos_geom


def _extrair_nome(feicao, indice):
    for campo in CAMPOS_NOME_CANDIDATOS:
        if campo in feicao.fields:
            valor = feicao.get(campo)
            if valor:
                return str(valor)
    return f"Estação importada {indice}"
