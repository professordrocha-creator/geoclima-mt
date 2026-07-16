# accounts/views.py
from django.contrib.auth import login
from django.shortcuts import redirect, render

from .forms import CadastroForm


def registrar(request):
    """
    Cadastro público. Ao salvar o form, o signal
    (accounts.signals.criar_profile_ao_criar_usuario) já cria o Profile
    com profile_type="produtor" — aqui só logamos o usuário e mandamos
    para o painel.
    """
    if request.user.is_authenticated:
        return redirect("dashboard:painel")

    if request.method == "POST":
        form = CadastroForm(request.POST)
        if form.is_valid():
            usuario = form.save()
            login(request, usuario)
            return redirect("dashboard:painel")
    else:
        form = CadastroForm()

    return render(request, "accounts/registro.html", {"form": form})
