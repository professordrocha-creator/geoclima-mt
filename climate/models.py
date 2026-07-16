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
    value = models.FloatField(verbose_name="Precipitação (mm)")
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

    def __str__(self):
        return f"{self.scenario} - {self.date}: {self.value} mm"
