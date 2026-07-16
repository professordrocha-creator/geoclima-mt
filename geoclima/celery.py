# geoclima/celery.py
import os
from celery import Celery
from celery.schedules import crontab

# Define o módulo de configurações padrão do Django para o programa 'celery'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'geoclima.settings')

app = Celery('geoclima')

# Usa as configurações do Django com prefixo CELERY_ (inclui CELERY_TIMEZONE
# = America/Cuiaba, definido em settings.py — o crontab abaixo é avaliado
# nesse fuso, não em UTC).
app.config_from_object('django.conf:settings', namespace='CELERY')

# Carrega tarefas de todos os aplicativos Django registrados
app.autodiscover_tasks()

# Agendamento (Etapa 3.3). Schedule estático em código — não usamos
# django-celery-beat (schedule editável via admin) porque, por enquanto,
# só existe UMA tarefa periódica fixa; ver docs/DECISOES.md.
app.conf.beat_schedule = {
    'atualizar-chirps-diario': {
        'task': 'climate.tasks.atualizar_chirps',
        # 04:00 America/Cuiaba, todo dia — horário de menor uso do sistema
        # e depois da janela normal de publicação diária do CHIRPS.
        'schedule': crontab(hour=4, minute=0),
    },
}

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
