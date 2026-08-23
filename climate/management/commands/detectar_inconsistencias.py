# climate/management/commands/detectar_inconsistencias.py
"""
Roda as 4 checagens de qualidade do dado local (Etapa 7.3 — chuva
negativa, valores extremos, duplicados, falhas temporais) e grava um
alerts.Alert (tipo 'inconsistency') pra cada achado.

Idempotente por (station, alert_type, message): a mesma inconsistência
não gera alerta duplicado se rodar de novo sem nada mudar no dado. Se o
dado mudar (ex.: o gap de falha temporal aumentar), a mensagem muda e
um novo alerta é criado — o antigo não é desativado automaticamente
(gerenciar o ciclo de vida do alerta é papel da Etapa 9, não desta
sub-etapa).

Uso:
    docker compose exec web python manage.py detectar_inconsistencias
"""
from django.core.management.base import BaseCommand

from alerts.models import Alert
from climate.quality_checks import rodar_todas_as_checagens


class Command(BaseCommand):
    help = "Detecta chuva negativa, valores extremos, duplicados e falhas temporais no dado local; grava Alert."

    def handle(self, *args, **options):
        achados = rodar_todas_as_checagens()

        if not achados:
            self.stdout.write(self.style.SUCCESS("Nenhuma inconsistência encontrada."))
            return

        criados = 0
        ja_existentes = 0

        for achado in achados:
            _, criado = Alert.objects.get_or_create(
                station=achado["station"],
                alert_type="inconsistency",
                message=achado["message"],
                defaults={"farm": achado["farm"], "owner": achado["owner"], "is_active": True},
            )
            if criado:
                criados += 1
                self.stdout.write(f"  {achado['message']}")
            else:
                ja_existentes += 1

        self.stdout.write(self.style.SUCCESS(
            f"\nDetecção concluída: {criados} alerta(s) novo(s), {ja_existentes} já existente(s)."
        ))
