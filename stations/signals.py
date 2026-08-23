# stations/signals.py
"""
Dispara o pipeline climático completo (SPI → cenários futuros →
alertas) automaticamente quando uma Station nova é cadastrada num
município que já tem CHIRPS suficiente — sem isso, o dashboard
mostrava "Ainda não há SPI suficiente" (e cenários/alertas vazios) até
alguém rodar os 3 comandos manualmente, nessa ordem.

Cobre os dois pontos de criação de estação que existem hoje (cadastro
normal em stations/views.py e criação automática a partir de Shapefile
em farms/views.py, que pode criar VÁRIAS estações numa única
requisição) porque os dois passam por Station.save() — um signal não
precisa saber qual view chamou.

`municipio.ativo` é o mesmo sinal já usado em todo o projeto (SPI,
validação, correção, projeções) pra "este município tem CHIRPS
importado" — não inventa um critério novo.

A chain (não uma task só) garante a ordem exigida: detectar_alertas
LÊ o SpiResult mais recente, então só pode rodar depois que calcular_spi
já tiver terminado. Assíncrono via Celery porque o pipeline inteiro
mede até ~77s em produção real (24-66s de calcular_spi + ~7s de
gerar_projecoes + ~4s de detectar_alertas_climaticos) — rodar isso
dentro do request de cadastro travaria a resposta. Ver docs/DECISOES.md.

Guarda de debounce (cache, TTL curto): sem isso, cadastrar N estações
de uma vez (o caso do Shapefile com N pontos) dispararia N chains
completas e redundantes pro mesmo município ao mesmo tempo — cada uma
recalculando o mesmo SPI/cenários/alertas que a chain anterior, ainda
em andamento, já está calculando. `cache.add()` é atômico (só grava se
a chave ainda não existe), evitando corrida entre requisições
concorrentes. Usa o backend de cache padrão do Django (LocMemCache,
sem configuração própria) — funciona porque a checagem roda sempre no
mesmo processo `web` (um serviço só, sem múltiplas réplicas hoje); se
o projeto um dia escalar `web` para múltiplos processos/containers,
esse cache deixa de ser compartilhado entre eles e a guarda perde
efeito — reavaliar um backend compartilhado (Redis, já usado pelo
Celery) nesse momento, não antes.
"""
from celery import chain
from django.core.cache import cache
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Station

# Tempo que a chain inteira normalmente leva pra terminar (ver medições
# em docs/DECISOES.md) + margem — nenhuma nova chain é disparada pro
# mesmo município enquanto esse tempo não passar desde o último disparo.
DEBOUNCE_SEGUNDOS = 120


@receiver(post_save, sender=Station)
def disparar_pipeline_climatico_ao_criar_estacao(sender, instance, created, **kwargs):
    if not created:
        return

    municipio = instance.farm.municipio
    if not municipio.ativo:
        return

    chave_debounce = f"pipeline_climatico_disparado:{municipio.codigo_ibge}"
    if not cache.add(chave_debounce, True, timeout=DEBOUNCE_SEGUNDOS):
        # Já existe uma chain recém-disparada pra este município — outra
        # estação do mesmo cadastro (ex.: Shapefile com vários pontos)
        # não precisa disparar uma segunda vez.
        return

    from climate.tasks import gerar_projecoes_task
    from spi.tasks import calcular_spi_municipio, detectar_alertas_climaticos_task

    chain(
        calcular_spi_municipio.si(municipio.codigo_ibge),
        gerar_projecoes_task.si(),
        detectar_alertas_climaticos_task.si(),
    ).delay()
