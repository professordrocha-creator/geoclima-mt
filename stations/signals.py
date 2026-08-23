# stations/signals.py
"""
Dispara o cálculo de SPI automaticamente quando uma Station nova é
cadastrada num município que já tem CHIRPS suficiente — sem isso, o
dashboard mostrava "Ainda não há SPI suficiente" até alguém rodar
`calcular_spi` manualmente.

Cobre os dois pontos de criação de estação que existem hoje (cadastro
normal em stations/views.py e criação automática a partir de Shapefile
em farms/views.py) porque os dois passam por Station.save() — um
signal não precisa saber qual view chamou.

`municipio.ativo` é o mesmo sinal já usado em todo o projeto (SPI,
validação, correção) pra "este município tem CHIRPS importado" — não
inventa um critério novo. Assíncrono via Celery porque calcular_spi
pra um município com décadas de histórico leva dezenas de segundos
(medido: ~24s pra 2 estações em Tangará da Serra) — rodar isso dentro
do request de cadastro travaria a resposta. Ver docs/DECISOES.md.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Station


@receiver(post_save, sender=Station)
def calcular_spi_ao_criar_estacao(sender, instance, created, **kwargs):
    if not created:
        return

    municipio = instance.farm.municipio
    if not municipio.ativo:
        return

    from spi.tasks import calcular_spi_municipio
    calcular_spi_municipio.delay(municipio.codigo_ibge)
