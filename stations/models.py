# stations/models.py
from django.contrib.gis.db import models
from django.contrib.auth.models import User
from farms.models import Farm

class Station(models.Model):
    STATION_TYPES = [
        ('davis', 'Davis'),
        ('ecowitt', 'Ecowitt'),
        ('ambient', 'Ambient Weather'),
        ('iot', 'IoT'),
        ('manual', 'Manual'),
        ('csv', 'CSV Importado'),
    ]

    name = models.CharField(max_length=255, verbose_name="Nome da Estação")
    station_type = models.CharField(max_length=50, choices=STATION_TYPES, default='manual', verbose_name="Tipo de Estação/Origem")
    latitude = models.FloatField(verbose_name="Latitude")
    longitude = models.FloatField(verbose_name="Longitude")
    
    # Campo espacial do PostGIS (Ponto da Estação)
    geom = models.PointField(srid=4326, verbose_name="Localização Espacial")
    
    # Relações de isolamento e hierarquia multiusuário
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='stations', verbose_name="Fazenda")
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='stations', verbose_name="Proprietário")

    def __str__(self):
        return f"{self.name} ({self.get_station_type_display()}) - {self.farm.name}"
