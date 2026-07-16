# accounts/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from .models import Profile


class ProfileInline(admin.StackedInline):
    """Mostra/edita o Profile (papel, telefone) direto na tela do usuário."""
    model = Profile
    can_delete = False
    verbose_name_plural = "Perfil"


class CustomUserAdmin(UserAdmin):
    # UserAdmin padrão do Django + a aba de Profile embutida, para o
    # administrador poder mudar o papel (profile_type) de qualquer
    # usuário sem precisar abrir a tela de Profile separadamente.
    inlines = (ProfileInline,)


# Troca o admin padrão do User pelo customizado com o Profile embutido.
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)

# Também registra o Profile avulso, para busca/filtro direto por papel.
@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "profile_type", "phone", "created_at")
    list_filter = ("profile_type",)
    search_fields = ("user__username", "user__email", "phone")
