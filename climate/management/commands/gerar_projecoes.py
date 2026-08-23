# climate/management/commands/gerar_projecoes.py
"""
Gera climate.Projection a partir da climatologia histórica do CHIRPS
(Etapa 10.2) — 3 cenários (seco/normal/úmido, percentis 25/50/75 do
histórico do mesmo mês do calendário) para os próximos meses, por
estação de cada município `ativo=True` (mesmo padrão de iteração de
`calcular_spi`/`detectar_alertas_climaticos` — o valor é o mesmo pra
todas as estações do município, redundância aceita, ver DECISOES.md).

NÃO é machine learning nem previsão de modelo climático — é
estatística descritiva (percentis) do histórico, deixado explícito na
UI também. Idempotente via `update_or_create` (station, date,
scenario).

Uso:
    docker compose exec web python manage.py gerar_projecoes
    docker compose exec web python manage.py gerar_projecoes --meses 12
"""
from django.core.management.base import BaseCommand

from climate.models import Projection
from climate.trends import cenarios_futuros
from maps.models import Municipio
from stations.models import Station


class Command(BaseCommand):
    help = "Gera cenários futuros (seco/normal/úmido) em climate.Projection a partir da climatologia histórica do CHIRPS."

    def add_arguments(self, parser):
        parser.add_argument("--meses", type=int, default=6, help="Quantos meses à frente gerar (padrão: 6).")

    def handle(self, *args, **options):
        meses = options["meses"]
        total_gravadas = 0

        for municipio in Municipio.objects.filter(ativo=True):
            cenarios = cenarios_futuros(municipio, meses=meses)
            if not cenarios:
                self.stdout.write(f"{municipio.nome}/{municipio.uf}: histórico insuficiente pra gerar cenário — pulando.")
                continue

            estacoes = Station.objects.filter(farm__municipio=municipio).select_related("farm", "owner")
            if not estacoes.exists():
                continue

            for estacao in estacoes:
                for mes in cenarios:
                    for cenario, valor in (("seco", mes["seco"]), ("normal", mes["normal"]), ("umido", mes["umido"])):
                        Projection.objects.update_or_create(
                            station=estacao, date=mes["date"], scenario=cenario,
                            defaults={"farm": estacao.farm, "owner": estacao.owner, "value": valor},
                        )
                        total_gravadas += 1

            self.stdout.write(
                f"{municipio.nome}/{municipio.uf}: {len(cenarios)} mes(es) × 3 cenários × "
                f"{estacoes.count()} estação(ões) (baseado em {cenarios[0]['n_anos']} anos de histórico)."
            )

        self.stdout.write(self.style.SUCCESS(f"\nGeração concluída: {total_gravadas} projeção(ões) gravada(s)/atualizada(s)."))
