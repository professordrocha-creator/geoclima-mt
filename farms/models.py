# farms/models.py
from django.contrib.gis.db import models
from django.contrib.auth.models import User

class Farm(models.Model):
    name = models.CharField(max_length=255, verbose_name="Nome da Fazenda")
    city = models.CharField(max_length=100, verbose_name="Município")
    latitude = models.FloatField(verbose_name="Latitude")
    longitude = models.FloatField(verbose_name="Longitude")
    area = models.FloatField(verbose_name="Área (hectares)", blank=True, null=True)
    crop = models.CharField(max_length=100, verbose_name="Cultura Agrícola", blank=True, null=True)
    notes = models.TextField(verbose_name="Observações", blank=True, null=True)
    
    # Campo espacial do PostGIS (Ponto georreferenciado)
    geom = models.PointField(srid=4326, verbose_name="Localização Espacial")
    
    # Campo obrigatório de isolamento multiusuário
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='farms', verbose_name="Proprietário")

    def __str__(self):
        return f"{self.name} - {self.city} ({self.owner.username})"
