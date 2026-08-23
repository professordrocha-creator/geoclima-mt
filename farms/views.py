# farms/views.py
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.gis.geos import Point
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify

from alerts.models import Alert
from climate.correction import serie_chirps_corrigida
from climate.models import ChirpsValidation, Projection
from climate.trends import tendencia_anual
from spi.models import SpiResult
from stations.models import Station
from .exports import gerar_workbook_fazenda
from .forms import FarmForm, TalhaoForm
from .models import Farm, Talhao
from .shapefile_import import processar_shapefile_zip


def _fazenda_do_usuario(request, farm_id):
    """
    Busca uma fazenda garantindo que pertence ao usuário logado.
    get_object_or_404 com owner=request.user na própria query — nunca
    filtramos "depois" de já ter o objeto, para não vazar dado de outro
    usuário nem por engano (isolamento multiusuário).
    """
    return get_object_or_404(Farm, pk=farm_id, owner=request.user)


def _processar_shapefile(request, form):
    """
    Lê request.FILES['shapefile'] (se enviado) e devolve o resultado da
    importação (farms.shapefile_import.ResultadoImportacaoShapefile) ou
    None se não veio nenhum arquivo. Em caso de erro de parsing, anexa o
    erro no próprio form (campo shapefile) e devolve None.
    """
    arquivo_shapefile = request.FILES.get("shapefile")
    if not arquivo_shapefile:
        return None
    try:
        return processar_shapefile_zip(arquivo_shapefile)
    except ValueError as exc:
        form.add_error("shapefile", str(exc))
        return None


def _criar_estacoes_do_shapefile(resultado_shapefile, fazenda, owner):
    """Cria uma Station por ponto encontrado no shapefile. Retorna quantas foram criadas."""
    if not resultado_shapefile:
        return 0
    criadas = 0
    for ponto in resultado_shapefile.pontos:
        Station.objects.create(
            name=ponto["nome"],
            station_type="manual",
            latitude=ponto["latitude"],
            longitude=ponto["longitude"],
            geom=Point(ponto["longitude"], ponto["latitude"], srid=4326),
            farm=fazenda,
            owner=owner,
        )
        criadas += 1
    return criadas


def _mensagem_resultado_shapefile(mensagem_base, resultado_shapefile, estacoes_criadas):
    if not resultado_shapefile:
        return mensagem_base
    if resultado_shapefile.poligono:
        mensagem_base += " Contorno importado do shapefile."
    if estacoes_criadas:
        mensagem_base += f" {estacoes_criadas} estação(ões) criada(s) automaticamente a partir do shapefile."
    return mensagem_base


@login_required
def lista_fazendas(request):
    fazendas = Farm.objects.filter(owner=request.user).select_related("municipio")
    return render(request, "farms/lista_fazendas.html", {"fazendas": fazendas})


@login_required
def criar_fazenda(request):
    if request.method == "POST":
        form = FarmForm(request.POST, request.FILES)
        if form.is_valid():
            fazenda = form.save(commit=False)
            fazenda.owner = request.user

            resultado_shapefile = _processar_shapefile(request, form)

            if resultado_shapefile and resultado_shapefile.poligono:
                # Shapefile com polígono manda mais que o clique no mapa —
                # a localização da fazenda vira o centroide do contorno importado.
                fazenda.poligono = resultado_shapefile.poligono
                centroide = resultado_shapefile.poligono.centroid
                fazenda.geom = centroide
                fazenda.latitude = centroide.y
                fazenda.longitude = centroide.x
            elif fazenda.latitude is None or fazenda.longitude is None:
                # Nem shapefile com polígono, nem clique no mapa: não dá
                # pra cadastrar a fazenda sem alguma localização.
                form.add_error(
                    None,
                    "Marque a localização no mapa ou envie um shapefile com um polígono da propriedade.",
                )

            if not form.errors:
                fazenda.save()
                estacoes_criadas = _criar_estacoes_do_shapefile(resultado_shapefile, fazenda, request.user)
                for aviso in (resultado_shapefile.avisos if resultado_shapefile else []):
                    messages.warning(request, aviso)
                messages.success(
                    request,
                    _mensagem_resultado_shapefile(
                        f"Fazenda \"{fazenda.name}\" cadastrada com sucesso.", resultado_shapefile, estacoes_criadas
                    ),
                )
                return redirect("farms:detalhe_fazenda", farm_id=fazenda.id)
    else:
        form = FarmForm()

    return render(request, "farms/form_fazenda.html", {"form": form, "editando": False})


@login_required
def editar_fazenda(request, farm_id):
    fazenda = _fazenda_do_usuario(request, farm_id)

    if request.method == "POST":
        # Guarda os valores anteriores antes do form mutar a instância —
        # se nem shapefile novo nem clique no mapa vierem nesta edição,
        # é isso que evita apagar a localização que já existia.
        latitude_anterior = fazenda.latitude
        longitude_anterior = fazenda.longitude
        geom_anterior = fazenda.geom
        poligono_anterior = fazenda.poligono

        form = FarmForm(request.POST, request.FILES, instance=fazenda)
        if form.is_valid():
            fazenda = form.save(commit=False)

            resultado_shapefile = _processar_shapefile(request, form)

            if resultado_shapefile and resultado_shapefile.poligono:
                fazenda.poligono = resultado_shapefile.poligono
                centroide = resultado_shapefile.poligono.centroid
                fazenda.geom = centroide
                fazenda.latitude = centroide.y
                fazenda.longitude = centroide.x
            elif fazenda.latitude is None or fazenda.longitude is None:
                fazenda.latitude = latitude_anterior
                fazenda.longitude = longitude_anterior
                fazenda.geom = geom_anterior
                fazenda.poligono = poligono_anterior

            if not form.errors:
                fazenda.save()
                estacoes_criadas = _criar_estacoes_do_shapefile(resultado_shapefile, fazenda, request.user)
                for aviso in (resultado_shapefile.avisos if resultado_shapefile else []):
                    messages.warning(request, aviso)
                messages.success(
                    request,
                    _mensagem_resultado_shapefile(
                        f"Fazenda \"{fazenda.name}\" atualizada.", resultado_shapefile, estacoes_criadas
                    ),
                )
                return redirect("farms:detalhe_fazenda", farm_id=fazenda.id)
    else:
        form = FarmForm(instance=fazenda)

    return render(request, "farms/form_fazenda.html", {"form": form, "editando": True, "fazenda": fazenda})


@login_required
def excluir_fazenda(request, farm_id):
    fazenda = _fazenda_do_usuario(request, farm_id)
    if request.method == "POST":
        nome = fazenda.name
        fazenda.delete()  # CASCADE apaga talhões e estações da fazenda junto
        messages.success(request, f"Fazenda \"{nome}\" e seus talhões/estações foram excluídos.")
        return redirect("farms:lista_fazendas")
    return render(request, "farms/confirmar_exclusao.html", {"objeto": fazenda, "tipo": "fazenda"})


def _dados_analiticos_fazenda(fazenda):
    """
    Todo o dado derivado (SPI, validação CHIRPS, correção, alertas,
    tendência, cenários) que `detalhe_fazenda.html` e
    `relatorio_fazenda.html` (Etapa 11 — exportação) mostram em comum.
    Extraído num helper pra não duplicar essas ~10 queries entre as
    views que precisam da mesma "foto" analítica da fazenda.
    """
    # SPI mais recente por escala (Etapa 7.1) — só existe se o município da
    # fazenda for ativo=True e o comando calcular_spi já tiver rodado.
    # Pega o resultado mais novo de qualquer estação da fazenda (o valor é
    # o mesmo pra todas, é um índice regional) por escala.
    spi_recente = (
        SpiResult.objects.filter(farm=fazenda)
        .order_by("scale", "-date")
        .distinct("scale")
    )

    # Validação CHIRPS × local (Etapa 7.2) — uma por estação que já tiver
    # dado local o suficiente pareado com CHIRPS pra calcular.
    validacoes_chirps = ChirpsValidation.objects.filter(farm=fazenda).select_related("station")

    # Inconsistências detectadas no dado local (Etapa 7.3) — só as ativas,
    # mais recentes primeiro (Alert.Meta.ordering já é -created_at).
    alertas_inconsistencia = Alert.objects.filter(
        farm=fazenda, alert_type="inconsistency", is_active=True
    )[:10]

    # Alertas climáticos derivados do SPI (Etapa 9.1) — seca, excesso de
    # chuva, risco hídrico, anomalia. Tipo diferente de 'inconsistency'
    # (que é sobre qualidade do DADO, não sobre o clima em si).
    alertas_climaticos = Alert.objects.filter(
        farm=fazenda,
        alert_type__in=["drought", "excess_rain", "water_risk", "anomaly"],
        is_active=True,
    )[:10]

    # Correção local do CHIRPS (Etapa 7.4) — só pras estações que já têm
    # validação (mbe) calculada; on-the-fly, não persiste série corrigida.
    correcoes_chirps = [
        {"station": validacao.station, "serie": serie_chirps_corrigida(validacao.station)}
        for validacao in validacoes_chirps
    ]

    # Tendência histórica (Etapa 10.1) — calculada on-the-fly, barata (só
    # totais anuais), mesmo espírito de climate/correction.py.
    tendencia = tendencia_anual(fazenda.municipio)

    # Cenários futuros (Etapa 10.2) — lidos de climate.Projection, gravados
    # pelo comando gerar_projecoes (mesmo padrão "rode o comando primeiro"
    # já usado em SPI/validação/alertas — não há agendamento automático
    # ainda, só o CHIRPS em si é atualizado sozinho via Celery Beat).
    projecoes_por_data = {}
    for projecao in Projection.objects.filter(farm=fazenda).order_by("date"):
        projecoes_por_data.setdefault(projecao.date, {})[projecao.scenario] = projecao.value
    cenarios = [
        {"date": data, "seco": valores.get("seco"), "normal": valores.get("normal"), "umido": valores.get("umido")}
        for data, valores in sorted(projecoes_por_data.items())
    ]

    return {
        "spi_recente": spi_recente, "validacoes_chirps": validacoes_chirps,
        "alertas_inconsistencia": alertas_inconsistencia,
        "alertas_climaticos": alertas_climaticos,
        "correcoes_chirps": correcoes_chirps,
        "tendencia": tendencia, "cenarios": cenarios,
    }


@login_required
def detalhe_fazenda(request, farm_id):
    fazenda = _fazenda_do_usuario(request, farm_id)
    talhoes = fazenda.talhoes.all()
    estacoes = fazenda.stations.all()

    return render(
        request,
        "farms/detalhe_fazenda.html",
        {
            "fazenda": fazenda, "talhoes": talhoes, "estacoes": estacoes,
            **_dados_analiticos_fazenda(fazenda),
        },
    )


@login_required
def relatorio_fazenda(request, farm_id):
    """
    Versão "pra imprimir" do detalhe da fazenda (Etapa 11) — mesmo
    dado de `detalhe_fazenda`, template diferente: sem navbar/menu, com
    CSS de impressão (`@media print`). O usuário aperta Ctrl+P e usa
    "Salvar como PDF" do próprio navegador — decisão explícita do
    usuário, pra não adicionar uma dependência pesada (WeasyPrint,
    exige libs de sistema) só pra gerar PDF no servidor. Ver
    docs/DECISOES.md.
    """
    fazenda = _fazenda_do_usuario(request, farm_id)
    talhoes = fazenda.talhoes.all()
    estacoes = fazenda.stations.all()

    return render(
        request,
        "farms/relatorio_fazenda.html",
        {
            "fazenda": fazenda, "talhoes": talhoes, "estacoes": estacoes,
            "gerado_em": timezone.now(),
            **_dados_analiticos_fazenda(fazenda),
        },
    )


@login_required
def exportar_fazenda_excel(request, farm_id):
    """
    Exporta todo o dado da fazenda pra um .xlsx com várias abas (Etapa
    11) — pra abrir em Excel, R, Python, SPSS etc. fora da plataforma.
    Reaproveita `openpyxl` (já é dependência do projeto desde a Etapa
    6, importação de planilha) — sem lib nova.
    """
    fazenda = _fazenda_do_usuario(request, farm_id)
    workbook = gerar_workbook_fazenda(fazenda)

    nome_arquivo = f"geoclima_{slugify(fazenda.name)}.xlsx"
    resposta = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    resposta["Content-Disposition"] = f'attachment; filename="{nome_arquivo}"'
    workbook.save(resposta)
    return resposta


@login_required
def criar_talhao(request, farm_id):
    fazenda = _fazenda_do_usuario(request, farm_id)

    if request.method == "POST":
        form = TalhaoForm(request.POST)
        if form.is_valid():
            talhao = form.save(commit=False)
            talhao.farm = fazenda
            talhao.owner = request.user
            talhao.save()
            messages.success(request, f"Talhão \"{talhao.name}\" cadastrado.")
            return redirect("farms:detalhe_fazenda", farm_id=fazenda.id)
    else:
        form = TalhaoForm()

    return render(
        request, "farms/form_talhao.html", {"form": form, "fazenda": fazenda, "editando": False}
    )


@login_required
def editar_talhao(request, farm_id, talhao_id):
    fazenda = _fazenda_do_usuario(request, farm_id)
    talhao = get_object_or_404(Talhao, pk=talhao_id, farm=fazenda, owner=request.user)

    if request.method == "POST":
        form = TalhaoForm(request.POST, instance=talhao)
        if form.is_valid():
            form.save()
            messages.success(request, f"Talhão \"{talhao.name}\" atualizado.")
            return redirect("farms:detalhe_fazenda", farm_id=fazenda.id)
    else:
        form = TalhaoForm(instance=talhao)

    return render(
        request,
        "farms/form_talhao.html",
        {"form": form, "fazenda": fazenda, "editando": True, "talhao": talhao},
    )


@login_required
def excluir_talhao(request, farm_id, talhao_id):
    fazenda = _fazenda_do_usuario(request, farm_id)
    talhao = get_object_or_404(Talhao, pk=talhao_id, farm=fazenda, owner=request.user)
    if request.method == "POST":
        nome = talhao.name
        talhao.delete()
        messages.success(request, f"Talhão \"{nome}\" excluído.")
        return redirect("farms:detalhe_fazenda", farm_id=fazenda.id)
    return render(request, "farms/confirmar_exclusao.html", {"objeto": talhao, "tipo": "talhão"})


@login_required
def poligono_fazenda_json(request, farm_id):
    """
    GeoJSON do contorno importado por shapefile (Farm.poligono), usado
    como camada de referência no mapa de cadastro de estação. Só o dono
    da fazenda acessa (mesma regra de isolamento das outras views).
    Retorna {"poligono": null} se a fazenda não tiver contorno importado.
    """
    fazenda = _fazenda_do_usuario(request, farm_id)
    if not fazenda.poligono:
        return JsonResponse({"poligono": None})
    return JsonResponse({"poligono": json.loads(fazenda.poligono.geojson)})
