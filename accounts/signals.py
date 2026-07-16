# accounts/signals.py
"""
Cria automaticamente um Profile para todo User novo (registro público,
createsuperuser, seed_demo, admin do Django etc.), com papel padrão
"produtor". get_or_create evita duplicar caso um Profile já tenha sido
criado explicitamente em outro lugar (ex.: seed_demo, que depois ajusta
o profile_type do admin_demo para "admin").
"""
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Profile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def criar_profile_ao_criar_usuario(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance, defaults={"profile_type": "produtor"})
