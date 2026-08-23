# climate/management/commands/validar_chirps.py
"""
Calcula a validação estatística CHIRPS × dado local (Etapa 7.2) pra
cada estação que tenha pelo menos um dado local lançado (manual ou
importado), gravando/atualizando climate.ChirpsValidation (um
resultado por estação, não uma série — reflete sempre o estado mais
recente do dado disponível).

Uso:
    docker compose exec web python manage.py validar_chirps
    docker compose exec web python manage.py validar_chirps --station 3
"""
from django.core.management.base import BaseCommand, CommandError

from climate.models import ChirpsValidation
from climate.validation import MINIMO_PARES, calcular_metricas, pares_chirps_local
from stations.models import Station


class Command(BaseCommand):
    help = "Calcula R²/RMSE/MAE/MBE/índice d/índice c comparando CHIRPS com dado local, por estação."

    def add_arguments(self, parser):
        parser.add_argument(
            "--station", type=int, default=None,
            help="ID de uma única estação. Padrão: todas as que têm dado local lançado.",
        )

    def handle(self, *args, **options):
        estacoes = Station.objects.select_related("farm", "farm__municipio", "owner")
        if options["station"]:
            estacoes = estacoes.filter(pk=options["station"])
            if not estacoes.exists():
                raise CommandError(f"Estação id={options['station']} não encontrada.")

        atualizadas = 0
        sem_dado_suficiente = 0

        for estacao in estacoes:
            pares = pares_chirps_local(estacao)
            metricas = calcular_metricas(pares)

            if metricas is None:
                if pares:
                    self.stdout.write(
                        f"{estacao.name}: só {len(pares)} dia(s) com CHIRPS+local pareados "
                        f"(mínimo {MINIMO_PARES}) — pulando."
                    )
                sem_dado_suficiente += 1
                continue

            ChirpsValidation.objects.update_or_create(
                station=estacao,
                defaults={
                    "farm": estacao.farm,
                    "owner": estacao.owner,
                    **metricas,
                },
            )
            atualizadas += 1
            self.stdout.write(
                f"{estacao.name}: n={metricas['n_pares']}, R²={metricas['r2']:.3f}, "
                f"RMSE={metricas['rmse']:.2f}mm, MBE={metricas['mbe']:.2f}mm, "
                f"c={metricas['indice_c']:.3f} ({metricas['desempenho_c']})"
            )

        self.stdout.write(self.style.SUCCESS(
            f"\nValidação concluída: {atualizadas} estação(ões) atualizada(s), "
            f"{sem_dado_suficiente} sem dado local pareado suficiente."
        ))
