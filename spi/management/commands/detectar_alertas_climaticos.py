# spi/management/commands/detectar_alertas_climaticos.py
"""
Gera alerts.Alert a partir do SPI mais recente (Etapa 9.1) — 4 tipos:
seca, excesso de chuva, risco hídrico, anomalia climática (critério de
cada um em spi/alert_checks.py).

Idempotente por (station, alert_type, message), mesmo padrão da Etapa
7.3 (climate/management/commands/detectar_inconsistencias.py). Como só
olha o valor MAIS RECENTE de cada escala, rodar de novo depois de um
novo `calcular_spi` atualiza os alertas automaticamente: se o mês/
condição mudar, a mensagem muda e um Alert novo é criado; o antigo
fica no histórico (não é desativado automaticamente — ciclo de vida
completo do alerta não é escopo desta geração).

Uso:
    docker compose exec web python manage.py detectar_alertas_climaticos
"""
from django.core.management.base import BaseCommand

from alerts.models import Alert
from spi.alert_checks import rodar_todas_as_checagens


class Command(BaseCommand):
    help = "Gera alertas automáticos (seca, excesso de chuva, risco hídrico, anomalia) a partir do SPI mais recente."

    def handle(self, *args, **options):
        achados = rodar_todas_as_checagens()

        if not achados:
            self.stdout.write(self.style.SUCCESS("Nenhuma condição de alerta climático encontrada."))
            return

        criados = 0
        ja_existentes = 0

        for achado in achados:
            _, criado = Alert.objects.get_or_create(
                station=achado["station"], alert_type=achado["alert_type"], message=achado["message"],
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
