# spi/tasks.py
"""
Task Celery que calcula o SPI de um município quando uma estação nova
é cadastrada nele (disparada por stations/signals.py). Não duplica a
lógica de cálculo/gravação — chama o próprio management command
`calcular_spi` via call_command, mesmo padrão já usado por
climate/tasks.py:atualizar_chirps com o import_chirps.

Roda pra TODAS as estações do município (não só a nova) — inofensivo,
o command já grava por update_or_create; é o mesmo resultado que rodar
`calcular_spi --municipio <código>` manualmente, só que automático.
"""
from celery import shared_task
from celery.utils.log import get_task_logger
from django.core.management import call_command

logger = get_task_logger(__name__)


@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
)
def calcular_spi_municipio(codigo_ibge):
    """
    Recalcula SPI-3/6/12 de todas as estações do município (código
    IBGE). Se o município não tiver CHIRPS suficiente, o próprio
    `calcular_spi` já lida com isso sem erro (não é papel desta task
    reimplementar essa checagem).
    """
    logger.info(f"Calculando SPI para município {codigo_ibge} (estação nova cadastrada).")
    call_command("calcular_spi", municipio=codigo_ibge)
