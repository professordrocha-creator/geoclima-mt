# stations/apps.py
from django.apps import AppConfig

class StationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'stations'

    def ready(self):
        import stations.signals  # noqa: F401 — registra o receiver do post_save
