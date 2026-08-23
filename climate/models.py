# climate/models.py
from django.contrib.gis.db import models
from django.contrib.auth.models import User
from farms.models import Farm
from stations.models import Station

class RainfallData(models.Model):
    SOURCE_TYPES = [
        ('chirps', 'CHIRPS'),
        ('manual', 'Manual'),
        ('station', 'Estação'),
        ('imported_csv', 'CSV Importado'),
        ('api', 'API Externa'),
    ]

    date = models.DateField(verbose_name="Data da Medição")
    # Horário e observações — pedidos explicitamente no PDF pra lançamento
    # manual ("chuva diária; horário; observações; anotações de campo"),
    # adicionados na Etapa 6. Opcionais: quem só quer registrar o total do
    # dia não é obrigado a informar hora.
    time = models.TimeField(verbose_name="Horário da Medição", blank=True, null=True)
    value = models.FloatField(verbose_name="Precipitação (mm)")
    notes = models.TextField(verbose_name="Observações", blank=True, null=True)
    source_type = models.CharField(max_length=50, choices=SOURCE_TYPES, default='manual', verbose_name="Origem do Dado")

    # Relações de isolamento multiusuário (Garantindo que todos os dados tenham owner_id, farm_id e station_id)
    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name='rainfall_records', verbose_name="Estação")
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='rainfall_records', verbose_name="Fazenda")
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='rainfall_records', verbose_name="Proprietário")

    class Meta:
        verbose_name = "Dado de Precipitação"
        verbose_name_plural = "Dados de Precipitação"
        unique_together = ('date', 'station', 'source_type')

    def __str__(self):
        return f"{self.date} - {self.value} mm ({self.get_source_type_display()}) - {self.station.name}"


class ChirpsData(models.Model):
    date = models.DateField(verbose_name="Data")
    value = models.FloatField(verbose_name="Precipitação Estimada (mm)")
    latitude = models.FloatField(verbose_name="Latitude")
    longitude = models.FloatField(verbose_name="Longitude")

    # Campo espacial do PostGIS. Para registros de média zonal por
    # município (Etapa 3.1), guarda o centroide do município — o polígono
    # completo mora em maps.Municipio.geom, não aqui.
    geom = models.PointField(srid=4326, verbose_name="Localização de Referência")

    # Município de onde veio a média zonal do CHIRPS. Nullable para não
    # quebrar o uso original do model como célula-grade pontual (sem
    # município associado); o command import_chirps sempre preenche este
    # campo. Ver docs/DECISOES.md (Etapa 3.1).
    municipio = models.ForeignKey(
        'maps.Municipio', on_delete=models.CASCADE, related_name='chirps_records',
        blank=True, null=True, verbose_name="Município (média zonal)",
    )

    # Relações opcionais para associar a grade de dados CHIRPS diretamente ao contexto multiusuário
    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name='chirps_records', blank=True, null=True, verbose_name="Estação")
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='chirps_records', blank=True, null=True, verbose_name="Fazenda")
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chirps_records', blank=True, null=True, verbose_name="Proprietário")

    class Meta:
        verbose_name = "Dado CHIRPS"
        verbose_name_plural = "Dados CHIRPS"
        # Postgres trata NULL como distinto em unique constraints, então
        # isso não impede múltiplos registros sem município — só bloqueia
        # duplicata quando município e data coincidem.
        unique_together = ('municipio', 'date')

    def __str__(self):
        if self.municipio_id:
            return f"CHIRPS {self.date} - {self.value} mm - {self.municipio.nome}/{self.municipio.uf}"
        return f"CHIRPS {self.date} - {self.value} mm - Lat: {self.latitude}, Lon: {self.longitude}"


class ChirpsValidation(models.Model):
    """
    Validação estatística CHIRPS × dado local de uma estação (Etapa 7.2).
    NÃO é uma série temporal — cada recálculo SUBSTITUI o resultado
    anterior da mesma estação (OneToOneField): é um retrato de "quão bem
    o CHIRPS bate com o que essa estação mede", atualizado sempre que o
    usuário lança/importa dado novo, não um histórico de validações.
    """

    DESEMPENHO_CHOICES = [
        ('otimo', 'Ótimo'),
        ('muito_bom', 'Muito Bom'),
        ('bom', 'Bom'),
        ('mediano', 'Mediano'),
        ('sofrivel', 'Sofrível'),
        ('mau', 'Mau'),
        ('pessimo', 'Péssimo'),
    ]

    station = models.OneToOneField(
        Station, on_delete=models.CASCADE, related_name='chirps_validation', verbose_name="Estação",
    )
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='chirps_validations', verbose_name="Fazenda")
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chirps_validations', verbose_name="Proprietário")

    n_pares = models.IntegerField(verbose_name="Nº de dias comparados")
    r2 = models.FloatField(verbose_name="R²")
    rmse = models.FloatField(verbose_name="RMSE (mm)")
    mae = models.FloatField(verbose_name="MAE (mm)")
    mbe = models.FloatField(verbose_name="MBE (mm) — viés médio")
    indice_d = models.FloatField(verbose_name="Índice d (Willmott)")
    indice_c = models.FloatField(verbose_name="Índice c (Camargo-Sentelhas)")
    desempenho_c = models.CharField(max_length=20, choices=DESEMPENHO_CHOICES, verbose_name="Desempenho (índice c)")

    calculado_em = models.DateTimeField(auto_now=True, verbose_name="Calculado em")

    class Meta:
        verbose_name = "Validação CHIRPS × Local"
        verbose_name_plural = "Validações CHIRPS × Local"

    def __str__(self):
        return f"{self.station.name}: R²={self.r2:.2f}, c={self.indice_c:.2f} ({self.get_desempenho_c_display()})"


class Projection(models.Model):
    date = models.DateField(verbose_name="Data da Projeção")
    scenario = models.CharField(max_length=100, verbose_name="Cenário Climático")
    value = models.FloatField(verbose_name="Precipitação Projetada (mm)")
    
    # Relações de isolamento multiusuário
    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name='projections', blank=True, null=True, verbose_name="Estação")
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='projections', blank=True, null=True, verbose_name="Fazenda")
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='projections', verbose_name="Proprietário")

    class Meta:
        verbose_name = "Projeção Climática"
        verbose_name_plural = "Projeções Climáticas"
        # Adicionado na Etapa 10.2 (gerar_projecoes precisa de
        # update_or_create idempotente, mesmo padrão de RainfallData/
        # SpiResult). scenario faz parte da chave porque um mesmo
        # (station, date) tem 3 linhas — uma por cenário (seco/normal/úmido).
        unique_together = ('date', 'scenario', 'station')

    def __str__(self):
        return f"{self.scenario} - {self.date}: {self.value} mm"
