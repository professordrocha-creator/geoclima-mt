# climate/management/commands/import_chirps.py
"""
Importa precipitação diária do CHIRPS via Google Earth Engine, como
MÉDIA ZONAL sobre o polígono de cada município com ativo=True em
maps.Municipio. O comando itera sobre os municípios ativos lidos do
banco — nenhuma cidade é citada por nome/código IBGE em lógica de
código aqui (ver docs/DECISOES.md, Etapa 2.2 e 3.1).

COLEÇÃO: UCSB-CHG/CHIRPS/DAILY (catálogo público do Earth Engine),
banda 'precipitation' (mm/dia), resolução nativa ~5,5 km (0.05°),
histórico desde 1981.

AUTENTICAÇÃO: conta de serviço do Google Cloud (projeto "climatga",
Earth Engine nível Comunidade). Variáveis de ambiente (já configuradas
no docker-compose.yml e espelhadas em geoclima/settings.py):
    GEE_PROJECT_ID=climatga
    GEE_SERVICE_ACCOUNT_KEY_PATH=/app/secrets/gee-key.json
A chave (secrets/gee-key.json) não é versionada — ver .gitignore. Para
recriar a conta de serviço do zero, ver o passo a passo registrado em
docs/HISTORICO.md (entrada de 2026-07-16, Etapa 3.1), que inclui os
papéis IAM necessários (Earth Engine Resource Viewer + Writer, e
Service Usage Consumer no projeto).

USO:
    # Últimos 30 dias, todos os municípios ativos (padrão)
    docker compose exec web python manage.py import_chirps

    # Período específico (--end é INCLUSIVO)
    docker compose exec web python manage.py import_chirps --start 2026-01-01 --end 2026-01-31

    # Só um município, pelo código IBGE (tem que estar ativo=True)
    docker compose exec web python manage.py import_chirps --municipio 5107958 --start 2026-01-01 --end 2026-01-31

    # Tamanho do bloco de processamento em dias (padrão: 365)
    docker compose exec web python manage.py import_chirps --start 1981-01-01 --end 2026-01-01 --chunk-days 365

BLOCOS: o Earth Engine tem limites de tempo/memória por requisição.
Períodos longos são processados em blocos de --chunk-days dias (padrão
365, ou seja, ano a ano). Dentro de cada bloco, a série diária inteira
é reduzida no lado do servidor via ImageCollection.map() — UMA chamada
.getInfo() traz todos os dias do bloco de uma vez, não um round-trip
por dia. O BACKFILL HISTÓRICO COMPLETO (desde 1981) é a Etapa 3.2, não
esta tarefa — aqui o mecanismo só foi validado com um período curto.

IDEMPOTÊNCIA: cada registro é gravado via update_or_create usando a
unique_together (municipio, date) de climate.ChirpsData como chave.
Rodar o mesmo período de novo atualiza os valores existentes em vez de
duplicar.
"""
import json
import os
from datetime import date, datetime, timedelta

import ee
from django.conf import settings
from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand, CommandError

from climate.models import ChirpsData
from maps.models import Municipio

CHIRPS_COLLECTION_ID = "UCSB-CHG/CHIRPS/DAILY"
CHIRPS_BAND = "precipitation"
CHIRPS_SCALE_METERS = 5566  # ~0.05°, resolução nativa do CHIRPS
DEFAULT_CHUNK_DAYS = 365


class Command(BaseCommand):
    help = "Importa precipitação diária do CHIRPS (Google Earth Engine) como média zonal por município ativo."

    def add_arguments(self, parser):
        parser.add_argument(
            "--start", type=str, default=None,
            help="Data inicial AAAA-MM-DD (padrão: hoje - 30 dias).",
        )
        parser.add_argument(
            "--end", type=str, default=None,
            help="Data final AAAA-MM-DD, INCLUSIVE (padrão: hoje).",
        )
        parser.add_argument(
            "--municipio", type=str, default=None,
            help="Código IBGE de um único município ativo (padrão: todos os ativos).",
        )
        parser.add_argument(
            "--chunk-days", type=int, default=DEFAULT_CHUNK_DAYS,
            help=f"Tamanho do bloco de processamento em dias (padrão: {DEFAULT_CHUNK_DAYS}).",
        )

    def handle(self, *args, **options):
        data_fim = self._parse_date(options["end"]) if options["end"] else date.today()
        data_inicio = (
            self._parse_date(options["start"]) if options["start"] else data_fim - timedelta(days=30)
        )
        if data_inicio > data_fim:
            raise CommandError("--start não pode ser depois de --end.")
        if options["chunk_days"] <= 0:
            raise CommandError("--chunk-days deve ser maior que zero.")

        municipios = Municipio.objects.filter(ativo=True)
        if options["municipio"]:
            municipios = municipios.filter(codigo_ibge=options["municipio"])
            if not municipios.exists():
                raise CommandError(
                    f"Nenhum município com ativo=True e codigo_ibge={options['municipio']!r} encontrado."
                )
        if not municipios.exists():
            raise CommandError(
                "Nenhum município com ativo=True encontrado. Rode import_municipios e marque "
                "algum município como ativo (maps.Municipio) antes de importar CHIRPS."
            )

        self._autenticar_gee()

        self.stdout.write(
            f"Período: {data_inicio.isoformat()} a {data_fim.isoformat()} (inclusive). "
            f"Municípios ativos selecionados: {municipios.count()}."
        )

        total_criados = 0
        total_atualizados = 0
        total_avisos = 0

        for municipio in municipios:
            self.stdout.write(f"\n== {municipio.nome}/{municipio.uf} (codigo_ibge={municipio.codigo_ibge}) ==")

            geometria_ee = ee.Geometry(json.loads(municipio.geom.geojson))
            centroide = municipio.geom.centroid  # x = longitude, y = latitude

            for bloco_inicio, bloco_fim in self._gerar_blocos(data_inicio, data_fim, options["chunk_days"]):
                self.stdout.write(f"  Bloco {bloco_inicio.isoformat()} a {bloco_fim.isoformat()}...")

                try:
                    dias = self._extrair_serie_zonal(geometria_ee, bloco_inicio, bloco_fim)
                except Exception as exc:
                    self.stderr.write(self.style.ERROR(
                        f"  Erro ao consultar o Earth Engine para {bloco_inicio}-{bloco_fim}: {exc}"
                    ))
                    total_avisos += 1
                    continue

                criados_bloco = 0
                atualizados_bloco = 0

                for feature in dias:
                    props = feature.get("properties", {})
                    data_str = props.get("date")
                    valor = props.get(CHIRPS_BAND)

                    if data_str is None or valor is None:
                        self.stderr.write(self.style.WARNING(
                            f"  Dia sem valor válido (possível falha de cobertura), pulando: {props}"
                        ))
                        total_avisos += 1
                        continue

                    _, criado = ChirpsData.objects.update_or_create(
                        municipio=municipio,
                        date=datetime.strptime(data_str, "%Y-%m-%d").date(),
                        defaults={
                            "value": valor,
                            "latitude": centroide.y,
                            "longitude": centroide.x,
                            "geom": Point(centroide.x, centroide.y, srid=4326),
                        },
                    )
                    if criado:
                        criados_bloco += 1
                    else:
                        atualizados_bloco += 1

                self.stdout.write(f"    {criados_bloco} novos, {atualizados_bloco} atualizados.")
                total_criados += criados_bloco
                total_atualizados += atualizados_bloco

        self.stdout.write(self.style.SUCCESS(
            f"\nImport concluído: {total_criados} registros novos, {total_atualizados} atualizados, "
            f"{total_avisos} avisos/erros."
        ))

    def _autenticar_gee(self):
        """Autentica no Earth Engine com a conta de serviço configurada."""
        key_path = settings.GEE_SERVICE_ACCOUNT_KEY_PATH
        project_id = settings.GEE_PROJECT_ID

        if not key_path or not project_id:
            raise CommandError(
                "GEE_PROJECT_ID e/ou GEE_SERVICE_ACCOUNT_KEY_PATH não configurados. "
                "Ver variáveis de ambiente no docker-compose.yml."
            )
        if not os.path.exists(key_path):
            raise CommandError(
                f"Chave da conta de serviço não encontrada em {key_path}. "
                "Ver docs/HISTORICO.md (2026-07-16) para o passo a passo de criação."
            )

        credenciais = ee.ServiceAccountCredentials(email=None, key_file=key_path)
        ee.Initialize(credenciais, project=project_id)
        self.stdout.write(f"Autenticado no Earth Engine (projeto {project_id}).")

    def _extrair_serie_zonal(self, geometria_ee, bloco_inicio, bloco_fim):
        """
        Reduz cada imagem diária do CHIRPS no bloco à média zonal sobre a
        geometria, no lado do servidor (ImageCollection.map), trazendo
        todo o bloco numa única chamada .getInfo() — não um round-trip
        por dia.
        """
        # filterDate trata o "end" como exclusivo no Earth Engine; somamos
        # 1 dia para que bloco_fim (inclusive, do ponto de vista do usuário)
        # entre na coleção.
        inicio_str = bloco_inicio.isoformat()
        fim_exclusivo_str = (bloco_fim + timedelta(days=1)).isoformat()

        colecao = ee.ImageCollection(CHIRPS_COLLECTION_ID).filterDate(inicio_str, fim_exclusivo_str)

        def reduzir_imagem(imagem):
            media = imagem.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=geometria_ee,
                scale=CHIRPS_SCALE_METERS,
                maxPixels=1e9,
            )
            return ee.Feature(None, {
                "date": imagem.date().format("YYYY-MM-dd"),
                CHIRPS_BAND: media.get(CHIRPS_BAND),
            })

        colecao_reduzida = colecao.map(reduzir_imagem)
        return colecao_reduzida.getInfo()["features"]

    def _gerar_blocos(self, data_inicio, data_fim, dias_por_bloco):
        """Divide [data_inicio, data_fim] em blocos consecutivos de até dias_por_bloco dias."""
        bloco_inicio = data_inicio
        while bloco_inicio <= data_fim:
            bloco_fim = min(bloco_inicio + timedelta(days=dias_por_bloco - 1), data_fim)
            yield bloco_inicio, bloco_fim
            bloco_inicio = bloco_fim + timedelta(days=1)

    @staticmethod
    def _parse_date(value):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            raise CommandError(f"Data inválida: {value!r} (use o formato AAAA-MM-DD).")
