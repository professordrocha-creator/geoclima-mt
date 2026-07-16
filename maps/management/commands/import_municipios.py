# maps/management/commands/import_municipios.py
"""
Importa a malha municipal do Brasil (IBGE) para a tabela maps.Municipio.

FONTE OFICIAL DO ARQUIVO (baixar manualmente antes de rodar este comando):
    Portal de Geociências do IBGE
    -> Malhas Territoriais
    -> Malhas Municipais
    -> municipio_2025
    -> Brasil
    URL do portal: https://www.ibge.gov.br/geociencias/organizacao-do-territorio/malhas-territoriais/15774-malhas.html

Baixe o shapefile "BR_Municipios_2025.zip" (~226 MB) e salve em:
    data/ibge/BR_Municipios_2025.zip

O arquivo NÃO é versionado no Git (ver .gitignore) por ser grande demais —
cada desenvolvedor precisa baixá-lo manualmente uma vez.

O comando lê o shapefile DIRETO de dentro do .zip (via /vsizip/ do GDAL),
sem precisar extrair os ~320 MB do .shp em disco. A geometria original vem
no datum SIRGAS2000 (SRID 4674); este comando reprojeta para WGS84
(SRID 4326, o mesmo usado pelo Leaflet/OpenStreetMap) e simplifica os
polígonos para não pesar o banco nem o navegador — os municípios maiores
têm dezenas de milhares de pontos no arquivo original.

Uso:
    # Importa o Brasil inteiro (~5.573 municípios, ~30s de processamento)
    docker compose exec web python manage.py import_municipios

    # Importa só um estado (mais rápido para testar)
    docker compose exec web python manage.py import_municipios --uf MT

    # Ajusta a tolerância de simplificação (graus decimais; padrão 0.0008,
    # equivalente a ~90 metros no equador — reduz o tamanho da geometria
    # em ~10-15x mantendo o contorno reconhecível em zoom de município)
    docker compose exec web python manage.py import_municipios --simplify 0.001

    # Desliga a simplificação (geometria completa do IBGE, mais pesada)
    docker compose exec web python manage.py import_municipios --no-simplify

Ao final da importação, o comando marca automaticamente os dois
municípios usados na validação científica da pesquisa de mestrado como
ativo=True e destaque=True — a marcação é feita por `codigo_ibge` (dado),
não por nome em lógica de código (ver docs/DECISOES.md):
    - Tangará da Serra / MT — código IBGE 5107958
    - Cáceres / MT         — código IBGE 5102504

Reexecutar o comando é seguro: cada município é gravado por upsert
(update_or_create) usando o codigo_ibge como chave.
"""
import os

from django.conf import settings
from django.contrib.gis.gdal import DataSource
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from maps.models import Municipio

# Caminho padrão do shapefile dentro do projeto (ver docstring acima).
SHAPEFILE_ZIP = os.path.join(settings.BASE_DIR, "data", "ibge", "BR_Municipios_2025.zip")
SHAPEFILE_NAME = "BR_Municipios_2025.shp"

# Tolerância de simplificação padrão (graus decimais). Documentada acima.
DEFAULT_SIMPLIFY_TOLERANCE = 0.0008

# Municípios usados na validação científica da pesquisa de mestrado.
# Único lugar do código onde esses nomes aparecem — e mesmo aqui a
# identificação é feita pelo código IBGE (dado oficial e imutável), não
# por comparação de string com o nome.
MUNICIPIOS_PESQUISA_CODIGOS_IBGE = {
    "5107958": "Tangará da Serra / MT",
    "5102504": "Cáceres / MT",
}


class Command(BaseCommand):
    help = "Importa a malha municipal do IBGE (data/ibge/BR_Municipios_2025.zip) para maps.Municipio."

    def add_arguments(self, parser):
        parser.add_argument(
            "--uf",
            type=str,
            default=None,
            help="Importa só os municípios da UF informada (ex.: MT). Padrão: Brasil inteiro.",
        )
        parser.add_argument(
            "--simplify",
            type=float,
            default=DEFAULT_SIMPLIFY_TOLERANCE,
            help=f"Tolerância de simplificação da geometria em graus (padrão: {DEFAULT_SIMPLIFY_TOLERANCE}).",
        )
        parser.add_argument(
            "--no-simplify",
            action="store_true",
            help="Desliga a simplificação e importa a geometria completa do IBGE (mais pesada).",
        )

    def handle(self, *args, **options):
        if not os.path.exists(SHAPEFILE_ZIP):
            raise CommandError(
                f"Arquivo não encontrado: {SHAPEFILE_ZIP}\n"
                "Baixe a malha municipal do IBGE (ver docstring deste comando "
                "para o link exato) e salve nesse caminho antes de rodar o import."
            )

        uf_filtro = options["uf"].upper() if options["uf"] else None
        tolerancia = None if options["no_simplify"] else options["simplify"]

        # GDAL lê o .shp direto de dentro do .zip, sem extrair em disco.
        vsizip_path = f"/vsizip/{SHAPEFILE_ZIP}/{SHAPEFILE_NAME}"
        datasource = DataSource(vsizip_path)
        layer = datasource[0]

        self.stdout.write(f"Malha municipal aberta: {len(layer)} municípios no arquivo.")
        if uf_filtro:
            self.stdout.write(f"Filtrando apenas UF={uf_filtro}.")
        if tolerancia:
            self.stdout.write(f"Simplificação de geometria ativada (tolerância={tolerancia}).")
        else:
            self.stdout.write("Simplificação de geometria DESLIGADA (--no-simplify).")

        criados = 0
        atualizados = 0
        ignorados = 0

        # Todo o import roda numa única transação: ou entra tudo, ou nada
        # fica pela metade se o processo cair no meio do caminho.
        with transaction.atomic():
            for feature in layer:
                sigla_uf = feature.get("SIGLA_UF")

                if uf_filtro and sigla_uf != uf_filtro:
                    ignorados += 1
                    continue

                codigo_ibge = feature.get("CD_MUN")
                nome = feature.get("NM_MUN")

                geom = self._processar_geometria(feature.geom, tolerancia)

                _, created = Municipio.objects.update_or_create(
                    codigo_ibge=codigo_ibge,
                    defaults={
                        "nome": nome,
                        "uf": sigla_uf,
                        "geom": geom,
                    },
                )
                if created:
                    criados += 1
                else:
                    atualizados += 1

            # Marca os municípios da pesquisa como ativo/destaque. Feito
            # por codigo_ibge (chave de dado), depois do import geral —
            # ver docs/DECISOES.md sobre por que isso não é uma condição
            # de código.
            marcados = 0
            for codigo, rotulo in MUNICIPIOS_PESQUISA_CODIGOS_IBGE.items():
                atualizadas = Municipio.objects.filter(codigo_ibge=codigo).update(
                    ativo=True, destaque=True
                )
                if atualizadas:
                    marcados += atualizadas
                    self.stdout.write(f"  -> {rotulo} (codigo_ibge={codigo}) marcado ativo/destaque.")
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  -> {rotulo} (codigo_ibge={codigo}) NÃO encontrado no import "
                            "(provavelmente --uf usado sem incluir MT)."
                        )
                    )

        self.stdout.write(
            self.style.SUCCESS(
                f"Import concluído: {criados} criados, {atualizados} atualizados, "
                f"{ignorados} ignorados (fora do filtro de UF), {marcados} marcados "
                "ativo/destaque."
            )
        )

    def _processar_geometria(self, gdal_geom, tolerancia):
        """Reprojeta para WGS84, simplifica (se pedido) e garante MultiPolygon."""
        gdal_geom.transform(4326)
        geos_geom = GEOSGeometry(gdal_geom.wkb, srid=4326)

        if tolerancia:
            geos_geom = geos_geom.simplify(tolerancia, preserve_topology=True)

        # A malha do IBGE traz Polygon; o model usa MultiPolygonField.
        if geos_geom.geom_type == "Polygon":
            geos_geom = MultiPolygon(geos_geom, srid=4326)
        geos_geom.srid = 4326

        return geos_geom
