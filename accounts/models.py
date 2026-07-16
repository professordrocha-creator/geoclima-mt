# accounts/models.py
from django.db import models
from django.contrib.auth.models import User

class Profile(models.Model):
    PROFILE_TYPES = [
        ('admin', 'Administrador'),
        ('pesquisador', 'Pesquisador'),
        ('produtor', 'Produtor'),
        ('tecnico', 'Técnico'),
        ('visitante', 'Visitante'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    profile_type = models.CharField(max_length=20, choices=PROFILE_TYPES, default='visitante')
    phone = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.user.username} - {self.get_profile_type_display()}"
