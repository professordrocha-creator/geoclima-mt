# stations/views.py
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from farms.models import Farm
from .forms import StationForm
from .models import Station


@login_required
def lista_estacoes(request):
    estacoes = Station.objects.filter(owner=request.user).select_related("farm")
    return render(request, "stations/lista_estacoes.html", {"estacoes": estacoes})


@login_required
def criar_estacao(request):
    if request.method == "POST":
        form = StationForm(request.POST, user=request.user)
        if form.is_valid():
            estacao = form.save(commit=False)
            estacao.owner = request.user
            estacao.save()
            messages.success(request, f"Estação \"{estacao.name}\" cadastrada com sucesso.")
            return redirect("stations:lista_estacoes")
    else:
        form = StationForm(user=request.user)

    # Coordenadas das fazendas do usuário, para o mapa recentralizar via
    # JS quando a fazenda escolhida no <select> mudar.
    fazendas = Farm.objects.filter(owner=request.user)
    return render(
        request, "stations/form_estacao.html", {"form": form, "editando": False, "fazendas": fazendas}
    )


@login_required
def editar_estacao(request, station_id):
    estacao = get_object_or_404(Station, pk=station_id, owner=request.user)

    if request.method == "POST":
        form = StationForm(request.POST, instance=estacao, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, f"Estação \"{estacao.name}\" atualizada.")
            return redirect("stations:lista_estacoes")
    else:
        form = StationForm(instance=estacao, user=request.user)

    fazendas = Farm.objects.filter(owner=request.user)
    return render(
        request,
        "stations/form_estacao.html",
        {"form": form, "editando": True, "estacao": estacao, "fazendas": fazendas},
    )


@login_required
def excluir_estacao(request, station_id):
    estacao = get_object_or_404(Station, pk=station_id, owner=request.user)
    if request.method == "POST":
        nome = estacao.name
        estacao.delete()
        messages.success(request, f"Estação \"{nome}\" excluída.")
        return redirect("stations:lista_estacoes")
    return render(request, "stations/confirmar_exclusao.html", {"objeto": estacao})
