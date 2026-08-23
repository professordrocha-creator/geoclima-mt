# climate/views.py
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from stations.models import Station
from .data_import import ErroImportacao, processar_arquivo
from .forms import ImportacaoArquivoForm, LancamentoManualForm
from .models import RainfallData


@login_required
def lista_lancamentos(request):
    """
    Histórico de lançamentos de chuva do usuário (manuais + importados —
    não mostra CHIRPS aqui, que é dado público, não do usuário).
    """
    lancamentos = (
        RainfallData.objects.filter(owner=request.user)
        .exclude(source_type="chirps")
        .select_related("station", "farm")
        .order_by("-date")
    )
    tem_estacao = Station.objects.filter(owner=request.user).exists()
    return render(
        request,
        "climate/lista_lancamentos.html",
        {"lancamentos": lancamentos, "tem_estacao": tem_estacao},
    )


@login_required
def criar_lancamento(request):
    if not Station.objects.filter(owner=request.user).exists():
        messages.info(request, "Cadastre uma estação antes de lançar dados de chuva.")
        return redirect("stations:criar_estacao")

    if request.method == "POST":
        form = LancamentoManualForm(request.POST, user=request.user)
        if form.is_valid():
            lancamento = form.save(commit=False)
            lancamento.owner = request.user
            lancamento.farm = lancamento.station.farm
            # Idempotente: relançar a mesma estação+data (fonte manual)
            # atualiza o registro existente em vez de dar erro de duplicidade.
            RainfallData.objects.update_or_create(
                station=lancamento.station,
                date=lancamento.date,
                source_type="manual",
                defaults={
                    "time": lancamento.time,
                    "value": lancamento.value,
                    "notes": lancamento.notes,
                    "farm": lancamento.farm,
                    "owner": request.user,
                },
            )
            messages.success(request, f"Chuva de {lancamento.date} lançada para {lancamento.station.name}.")
            return redirect("climate:lista_lancamentos")
    else:
        form = LancamentoManualForm(user=request.user)

    return render(request, "climate/form_lancamento.html", {"form": form, "editando": False})


@login_required
def editar_lancamento(request, lancamento_id):
    lancamento = get_object_or_404(RainfallData, pk=lancamento_id, owner=request.user)

    if request.method == "POST":
        form = LancamentoManualForm(request.POST, instance=lancamento, user=request.user)
        if form.is_valid():
            editado = form.save(commit=False)
            editado.farm = editado.station.farm
            editado.save()
            messages.success(request, "Lançamento atualizado.")
            return redirect("climate:lista_lancamentos")
    else:
        form = LancamentoManualForm(instance=lancamento, user=request.user)

    return render(
        request, "climate/form_lancamento.html", {"form": form, "editando": True, "lancamento": lancamento}
    )


@login_required
def excluir_lancamento(request, lancamento_id):
    lancamento = get_object_or_404(RainfallData, pk=lancamento_id, owner=request.user)
    if request.method == "POST":
        lancamento.delete()
        messages.success(request, "Lançamento excluído.")
        return redirect("climate:lista_lancamentos")
    return render(request, "climate/confirmar_exclusao.html", {"objeto": lancamento})


@login_required
def importar_arquivo(request):
    if not Station.objects.filter(owner=request.user).exists():
        messages.info(request, "Cadastre uma estação antes de importar um arquivo.")
        return redirect("stations:criar_estacao")

    if request.method == "POST":
        form = ImportacaoArquivoForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            station = form.cleaned_data["station"]
            arquivo = form.cleaned_data["arquivo"]
            try:
                registros, erros_linha = processar_arquivo(arquivo)
            except ErroImportacao as exc:
                form.add_error("arquivo", str(exc))
            else:
                criados = 0
                atualizados = 0
                for registro in registros:
                    _, criado = RainfallData.objects.update_or_create(
                        station=station,
                        date=registro["date"],
                        source_type="imported_csv",
                        defaults={
                            "time": registro["time"],
                            "value": registro["value"],
                            "notes": registro["notes"],
                            "farm": station.farm,
                            "owner": request.user,
                        },
                    )
                    if criado:
                        criados += 1
                    else:
                        atualizados += 1

                mensagem = f"Importação concluída: {criados} registros novos, {atualizados} atualizados."
                if erros_linha:
                    mensagem += f" {len(erros_linha)} linha(s) ignorada(s) por erro de formato."
                messages.success(request, mensagem)
                for erro in erros_linha[:10]:  # não inunda a tela se o arquivo tiver muita linha ruim
                    messages.warning(request, erro)
                return redirect("climate:lista_lancamentos")
    else:
        form = ImportacaoArquivoForm(user=request.user)

    return render(request, "climate/form_importar.html", {"form": form})
