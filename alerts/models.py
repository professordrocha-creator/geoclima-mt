# alerts/models.py
from django.db import models
from django.contrib.auth.models import User
from farms.models import Farm
from stations.models import Station

class Alert(models.Model):
    ALERT_TYPES = [
        ('drought', 'Alerta de Seca'),
        ('excess_rain', 'Alerta de Excesso de Chuva'),
        ('water_risk', 'Risco Hídrico'),
        ('anomaly', 'Anomalia Climática'),
        # Adicionado na Etapa 7.3 — detecção de inconsistências no dado
        # local (chuva negativa, valor extremo, duplicado, falha
        # temporal). Diferente de 'anomaly' (que é sobre o CLIMA em si,
        # Etapa 9): este tipo é sobre a QUALIDADE do dado lançado.
        ('inconsistency', 'Possível Inconsistência'),
    ]

    alert_type = models.CharField(max_length=50, choices=ALERT_TYPES, verbose_name="Tipo de Alerta")
    message = models.TextField(verbose_name="Mensagem do Alerta")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Criado em")
    is_active = models.BooleanField(default=True, verbose_name="Ativo")

    # Relações de isolamento multiusuário (Garantindo owner_id, farm_id e station_id)
    station = models.ForeignKey(Station, on_delete=models.CASCADE, related_name='alerts', blank=True, null=True, verbose_name="Estação")
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name='alerts', blank=True, null=True, verbose_name="Fazenda")
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='alerts', verbose_name="Proprietário")

    class Meta:
        verbose_name = "Alerta Climático"
        verbose_name_plural = "Alertas Climáticos"
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.get_alert_type_display()}] {self.farm.name if self.farm else 'Global'} - {self.created_at.strftime('%d/%m/%Y %H:%M')}"
