# spi/models.py
from django.db import models
from django.contrib.auth.models import User
from farms.models import Farm
from stations.models import Station

class SpiResult(models.Model):
    CLASSIFICATIONS = [
        ('extremamente_umido', 'Extremamente Úmido'),
        ('muito_umido', 'Muito Úmido'),
        ('normal', 'Normal'),
        ('seca_moderada', 'Seca Moderada'),
        ('seca_severa', 'Seca Severa'),
        ('seca_extrema', 'Seca Extrema'),
    ]

    date = models.DateField(verbose_name="Data do Cálculo")
    scale = models.IntegerField(choices=[(3, 'SPI-3'), (6, 'SPI-6'), (12, 'SPI-12')], verbose_name="Escala Temporal (meses)")
    value = models.FloatField(verbose_name="Valor do SPI")
    classification = models.CharField(max_length=50, choices=CLASSIFICATIONS, verbose_name="Classificação")

    # Relações de isolamento multiusuário
    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name='spi_results', verbose_name="Estação")
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='spi_results', verbose_name="Fazenda")
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='spi_results', verbose_name="Proprietário")

    class Meta:
        verbose_name = "Resultado do SPI"
        verbose_name_plural = "Resultados do SPI"
        unique_together = ('date', 'scale', 'station')

    def __str__(self):
        return f"{self.station.name} - SPI-{self.scale} ({self.date}): {self.value:.2f} ({self.get_classification_display()})"
