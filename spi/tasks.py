# spi/tasks.py
"""
Tasks Celery do pipeline climático disparado quando uma estação nova é
cadastrada (stations/signals.py). Nenhuma reimplementa lógica de
cálculo — cada uma só chama o management command correspondente via
call_command, mesmo padrão já usado por climate/tasks.py:atualizar_chirps
com o import_chirps. `calcular_spi_municipio` e
`detectar_alertas_climaticos_task` moram aqui porque são os commands
do app `spi`; `gerar_projecoes_task` mora em climate/tasks.py, mesmo
critério (command do app `climate`).

As três são encadeadas via `celery.chain` (não uma task só) porque
`detectar_alertas_climaticos` LÊ o SpiResult mais recente — rodar fora
de ordem (alertas antes do SPI atualizado) gera alerta desatualizado
ou vazio. `chain` garante que uma etapa só roda depois que a anterior
termina, com retry independente por etapa. Ver docs/DECISOES.md.
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


@shared_task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
)
def detectar_alertas_climaticos_task():
    """
    Última etapa da chain — gera alertas climáticos (seca, excesso de
    chuva, risco hídrico, anomalia) a partir do SPI mais recente.
    `detectar_alertas_climaticos` não aceita filtro por município (roda
    sobre o SpiResult mais recente de TODAS as estações do banco) —
    por isso não recebe `codigo_ibge` nenhum, e por isso só pode rodar
    depois que a etapa de SPI da chain já tiver terminado.
    """
    logger.info("Detectando alertas climáticos (após recálculo de SPI).")
    call_command("detectar_alertas_climaticos")
