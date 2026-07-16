# accounts/management/commands/seed_demo.py
"""
Cria usuários de teste reprodutíveis para desenvolvimento (Etapa 4).

>>> SOMENTE DESENVOLVIMENTO <<<
As credenciais criadas aqui são públicas (documentadas no README.md) e
NUNCA devem existir num ambiente de produção/beta público. Por isso o
comando se recusa a rodar se DEBUG=False, a menos que --force seja
passado explicitamente.

Cria (idempotente — reexecutar não duplica nem reseta senha de quem já
existe):
    a) admin_demo — superusuário, Profile.profile_type = "admin".
    b) joao.produtor — usuário comum "João da Silva",
       Profile.profile_type = "produtor". NÃO cria fazenda (Etapa 5).

Uso:
    docker compose exec web python manage.py seed_demo
"""
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from accounts.models import Profile

# Credenciais de desenvolvimento — documentadas também no README.md.
ADMIN_DEMO_USERNAME = "admin_demo"
ADMIN_DEMO_PASSWORD = "AdminDemo#2026"
ADMIN_DEMO_EMAIL = "admin_demo@geoclima.mt"

PRODUTOR_DEMO_USERNAME = "joao.produtor"
PRODUTOR_DEMO_PASSWORD = "Produtor#2026"
PRODUTOR_DEMO_EMAIL = "joao.produtor@geoclima.mt"
PRODUTOR_DEMO_NOME = "João"
PRODUTOR_DEMO_SOBRENOME = "da Silva"


class Command(BaseCommand):
    help = "Cria usuários de teste (admin_demo, joao.produtor) — SOMENTE DESENVOLVIMENTO."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Permite rodar mesmo com DEBUG=False. Não use isso em produção de verdade.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "DEBUG=False — este comando cria usuários com senha pública e conhecida, "
                "não deve rodar fora de desenvolvimento. Use --force se tiver certeza absoluta "
                "do que está fazendo."
            )

        self._criar_admin_demo()
        self._criar_produtor_demo()

        self.stdout.write(self.style.WARNING(
            "\nLembrete: essas credenciais são de DESENVOLVIMENTO apenas, documentadas no "
            "README.md. Nunca usar em produção."
        ))

    def _criar_admin_demo(self):
        usuario, criado = User.objects.get_or_create(
            username=ADMIN_DEMO_USERNAME,
            defaults={
                "email": ADMIN_DEMO_EMAIL,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if criado:
            usuario.set_password(ADMIN_DEMO_PASSWORD)
            usuario.save()
            self.stdout.write(self.style.SUCCESS(f"Superusuário '{ADMIN_DEMO_USERNAME}' criado."))
        else:
            self.stdout.write(f"Superusuário '{ADMIN_DEMO_USERNAME}' já existia — senha não foi alterada.")

        # O signal (accounts/signals.py) já criou um Profile com
        # profile_type="produtor" por padrão; aqui promovemos para
        # "admin", já que admin_demo representa um administrador.
        profile, _ = Profile.objects.get_or_create(user=usuario)
        if profile.profile_type != "admin":
            profile.profile_type = "admin"
            profile.save()

    def _criar_produtor_demo(self):
        usuario, criado = User.objects.get_or_create(
            username=PRODUTOR_DEMO_USERNAME,
            defaults={
                "email": PRODUTOR_DEMO_EMAIL,
                "first_name": PRODUTOR_DEMO_NOME,
                "last_name": PRODUTOR_DEMO_SOBRENOME,
            },
        )
        if criado:
            usuario.set_password(PRODUTOR_DEMO_PASSWORD)
            usuario.save()
            self.stdout.write(self.style.SUCCESS(
                f"Usuário '{PRODUTOR_DEMO_USERNAME}' ({PRODUTOR_DEMO_NOME} {PRODUTOR_DEMO_SOBRENOME}) criado."
            ))
        else:
            self.stdout.write(f"Usuário '{PRODUTOR_DEMO_USERNAME}' já existia — senha não foi alterada.")

        # Já vem "produtor" por padrão via signal, mas deixamos explícito
        # aqui para o comando não depender silenciosamente do signal.
        profile, _ = Profile.objects.get_or_create(user=usuario)
        if profile.profile_type != "produtor":
            profile.profile_type = "produtor"
            profile.save()
