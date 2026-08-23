# spi/management/commands/calcular_spi.py
"""
Calcula o SPI (Etapa 7.1) para os municípios com ativo=True e grava em
spi.SpiResult, um registro por estação cadastrada numa fazenda desse
município (o valor do SPI é o mesmo pra todas as estações do mesmo
município — é um índice regional, calculado a partir do CHIRPS — mas
fica gravado por estação porque é assim que o model já isola por
usuário).

Nenhum município é citado por nome no código — itera sobre
maps.Municipio.objects.filter(ativo=True). Só funciona pra quem tiver
CHIRPS importado (ver climate/management/commands/import_chirps.py) e
pelo menos uma estação cadastrada numa fazenda desse município.

Uso:
    docker compose exec web python manage.py calcular_spi
    docker compose exec web python manage.py calcular_spi --scale 3
    docker compose exec web python manage.py calcular_spi --municipio 5107958
"""
from django.core.management.base import BaseCommand, CommandError

from maps.models import Municipio
from spi.models import SpiResult
from spi.services import ESCALAS_VALIDAS, calcular_serie_spi
from stations.models import Station


class Command(BaseCommand):
    help = "Calcula SPI-3/6/12 para municípios ativos e grava por estação (spi.SpiResult)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--scale", type=int, choices=ESCALAS_VALIDAS, default=None,
            help="Só uma escala (3, 6 ou 12). Padrão: todas as três.",
        )
        parser.add_argument(
            "--municipio", type=str, default=None,
            help="Código IBGE de um único município ativo. Padrão: todos os ativos.",
        )

    def handle(self, *args, **options):
        escalas = [options["scale"]] if options["scale"] else list(ESCALAS_VALIDAS)

        municipios = Municipio.objects.filter(ativo=True)
        if options["municipio"]:
            municipios = municipios.filter(codigo_ibge=options["municipio"])
            if not municipios.exists():
                raise CommandError(
                    f"Nenhum município ativo=True com codigo_ibge={options['municipio']!r}."
                )
        if not municipios.exists():
            raise CommandError("Nenhum município com ativo=True encontrado.")

        total_gravados = 0
        total_atualizados = 0

        for municipio in municipios:
            estacoes = Station.objects.filter(farm__municipio=municipio).select_related("farm", "owner")
            if not estacoes.exists():
                self.stdout.write(
                    self.style.WARNING(
                        f"{municipio.nome}/{municipio.uf}: nenhuma estação cadastrada em fazenda "
                        "desse município ainda — nada a gravar (SPI calculado, mas sem onde salvar)."
                    )
                )
                continue

            self.stdout.write(f"\n== {municipio.nome}/{municipio.uf} — {estacoes.count()} estação(ões) ==")

            for escala in escalas:
                serie = calcular_serie_spi(municipio, escala)
                if not serie:
                    self.stdout.write(
                        self.style.WARNING(f"  SPI-{escala}: histórico insuficiente, nenhum valor calculado.")
                    )
                    continue

                self.stdout.write(f"  SPI-{escala}: {len(serie)} meses calculados.")

                for estacao in estacoes:
                    for ponto in serie:
                        _, criado = SpiResult.objects.update_or_create(
                            station=estacao, scale=escala, date=ponto["date"],
                            defaults={
                                "value": ponto["value"],
                                "classification": ponto["classification"],
                                "farm": estacao.farm,
                                "owner": estacao.owner,
                            },
                        )
                        if criado:
                            total_gravados += 1
                        else:
                            total_atualizados += 1

        self.stdout.write(self.style.SUCCESS(
            f"\nCálculo concluído: {total_gravados} registros novos, {total_atualizados} atualizados."
        ))
