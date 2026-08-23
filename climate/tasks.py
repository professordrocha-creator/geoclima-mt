# climate/tasks.py
"""
Task Celery de atualização automática diária do CHIRPS (Etapa 3.3).

Agendada em geoclima/celery.py (beat_schedule) para rodar todo dia às
04:00 (horário de Cuiabá). Mantém climate.ChirpsData em dia para cada
município com ativo=True SEM reprocessar o histórico inteiro: para cada
município, descobre a última data já gravada no banco e importa só o
que falta, até a última data publicada pelo CHIRPS no Earth Engine.

Reaproveita o management command import_chirps (Etapa 3.1) via
call_command — a lógica de extração/reduceRegion continua existindo em
um único lugar (climate/management/commands/import_chirps.py); esta
task só decide QUAL período pedir para cada município. Ver
docs/DECISOES.md.
"""
from datetime import datetime, timedelta

import ee
from celery import shared_task
from celery.utils.log import get_task_logger
from django.conf import settings
from django.core.management import call_command
from django.db.models import Max

from climate.models import ChirpsData
from maps.models import Municipio

logger = get_task_logger(__name__)

CHIRPS_COLLECTION_ID = "UCSB-CHG/CHIRPS/DAILY"


def _obter_ultima_data_disponivel_no_gee():
    """Autentica no Earth Engine e retorna a data da imagem CHIRPS mais recente publicada."""
    credenciais = ee.ServiceAccountCredentials(email=None, key_file=settings.GEE_SERVICE_ACCOUNT_KEY_PATH)
    ee.Initialize(credenciais, project=settings.GEE_PROJECT_ID)

    colecao = ee.ImageCollection(CHIRPS_COLLECTION_ID)
    ultima_imagem = colecao.sort("system:time_start", False).first()
    # 'system:index' de cada imagem do CHIRPS/DAILY é a própria data, no
    # formato AAAAMMDD (ex.: '20260630').
    indice = ultima_imagem.get("system:index").getInfo()
    return datetime.strptime(indice, "%Y%m%d").date()


@shared_task(
    bind=True,
    autoretry_for=(Exception,),  # qualquer falha (rede, GEE fora do ar, etc.) aciona retry
    retry_backoff=True,          # backoff exponencial: 1, 2, 4, 8... minutos
    retry_backoff_max=600,       # nunca espera mais que 10 min entre tentativas
    retry_jitter=True,
    max_retries=5,
)
def atualizar_chirps(self):
    """
    Atualização incremental diária do CHIRPS para todos os municípios
    ativos. Idempotente e seguro de rodar mais de uma vez no mesmo dia
    (import_chirps já faz upsert por município+data).
    """
    ultima_data_gee = _obter_ultima_data_disponivel_no_gee()
    logger.info(f"Última data disponível no CHIRPS (Earth Engine): {ultima_data_gee.isoformat()}")

    municipios = Municipio.objects.filter(ativo=True)
    if not municipios.exists():
        logger.warning("Nenhum município com ativo=True — nada a atualizar.")
        return "sem municípios ativos"

    falhas = []
    atualizados = []
    sem_novidade = []

    for municipio in municipios:
        ultima_data_gravada = (
            ChirpsData.objects.filter(municipio=municipio).aggregate(Max("date"))["date__max"]
        )

        if ultima_data_gravada is None:
            # Município ativo mas nunca importado — isso é o backfill
            # (Etapa 3.2), não o papel desta task de atualização
            # incremental. Só avisa e segue para o próximo município.
            logger.warning(
                f"{municipio.nome}/{municipio.uf}: nenhum dado gravado ainda em ChirpsData. "
                "Rode o backfill (import_chirps) manualmente antes de contar com a atualização automática."
            )
            continue

        proximo_dia = ultima_data_gravada + timedelta(days=1)

        if proximo_dia > ultima_data_gee:
            # Isso é o caso normal e esperado no dia a dia (defasagem de
            # publicação do CHIRPS) — não é erro.
            logger.info(
                f"{municipio.nome}/{municipio.uf}: sem dados novos "
                f"(última gravada={ultima_data_gravada.isoformat()}, "
                f"última publicada={ultima_data_gee.isoformat()})."
            )
            sem_novidade.append(municipio.nome)
            continue

        logger.info(
            f"{municipio.nome}/{municipio.uf}: importando {proximo_dia.isoformat()} "
            f"a {ultima_data_gee.isoformat()}..."
        )
        try:
            call_command(
                "import_chirps",
                municipio=municipio.codigo_ibge,
                start=proximo_dia.isoformat(),
                end=ultima_data_gee.isoformat(),
            )
            atualizados.append(municipio.nome)
        except Exception as exc:
            logger.error(f"{municipio.nome}/{municipio.uf}: falha ao importar — {exc}")
            falhas.append(municipio.nome)

    resumo = f"atualizados={atualizados} sem_novidade={sem_novidade} falhas={falhas}"
    logger.info(f"Atualização diária do CHIRPS concluída. {resumo}")

    if falhas:
        # Levanta erro para acionar o retry automático (autoretry_for)
        # do Celery — só para os municípios que realmente falharam; os
        # que já foram atualizados/confirmados sem novidade não são
        # reprocessados à toa graças ao upsert idempotente do import_chirps.
        raise RuntimeError(f"Falha ao atualizar CHIRPS para: {', '.join(falhas)}")

    return resumo


@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
)
def gerar_projecoes_task():
    """
    Segunda etapa da chain disparada ao cadastrar estação nova (ver
    spi/tasks.py e stations/signals.py) — gera cenários futuros a
    partir da climatologia histórica. `gerar_projecoes` não aceita
    filtro por município (roda sobre todos os `ativo=True` de uma
    vez), por isso não recebe nenhum argumento aqui.
    """
    logger.info("Gerando cenários futuros (climatologia histórica).")
    call_command("gerar_projecoes")
