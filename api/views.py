# api/views.py
import json

from django.contrib.gis.geos import Point
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.text import slugify

from climate import municipio_indicators as mi
from climate.models import ChirpsData
from climate.municipio_exports import gerar_workbook_municipio
from maps.models import Municipio

# Escalas de SPI expostas na home pública, com rótulo curto explicando o
# horizonte de cada uma (pedido explícito do usuário — as 4 escalas juntas,
# não só 3/6). Mesma ordem em que aparecem no frontend.
ESCALAS_SPI_HOME = [
    (1, "último mês"),
    (3, "trimestre"),
    (6, "semestre"),
    (12, "ano"),
]

# Nomes por extenso das 27 UFs do Brasil. É uma tabela de referência fixa
# (o conjunto de UFs não muda), usada só para exibição no seletor — não
# tem relação com o recorte de pesquisa (Tangará da Serra/Cáceres) e não
# filtra nada; ver docs/DECISOES.md.
UF_NOMES = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas",
    "BA": "Bahia", "CE": "Ceará", "DF": "Distrito Federal",
    "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão",
    "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais",
    "PA": "Pará", "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco",
    "PI": "Piauí", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
    "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima",
    "SC": "Santa Catarina", "SP": "São Paulo", "SE": "Sergipe",
    "TO": "Tocantins",
}


def estados_list(request):
    """GET /api/estados/ — UFs distintas presentes na tabela maps.Municipio."""
    siglas = Municipio.objects.order_by("uf").values_list("uf", flat=True).distinct()
    data = [{"sigla": sigla, "nome": UF_NOMES.get(sigla, sigla)} for sigla in siglas]
    return JsonResponse(data, safe=False)


def municipios_list(request):
    """
    GET /api/municipios/?uf=MT — municípios de uma UF.

    Resposta leve (sem geometria): id, nome, codigo_ibge, destaque.
    Ordenado com os municípios em destaque primeiro, depois alfabético.
    """
    uf = request.GET.get("uf", "").strip().upper()
    if not uf:
        return JsonResponse({"erro": "Parâmetro 'uf' é obrigatório."}, status=400)

    municipios = (
        Municipio.objects.filter(uf=uf)
        .order_by("-destaque", "nome")
        .values("id", "nome", "codigo_ibge", "destaque")
    )
    return JsonResponse(list(municipios), safe=False)


def municipio_geojson(request, municipio_id):
    """
    GET /api/municipios/<id>/geojson/ — polígono do município para desenhar
    no Leaflet. A geometria só é retornada aqui (nunca na listagem), e o
    centroide vem pronto nas properties para o frontend não precisar
    recalcular (nem depender de libs tipo turf.js) para recarregar o clima.
    """
    municipio = get_object_or_404(Municipio, pk=municipio_id)
    centroide = municipio.geom.centroid  # x = longitude, y = latitude

    feature = {
        "type": "Feature",
        "geometry": json.loads(municipio.geom.geojson),
        "properties": {
            "id": municipio.id,
            "nome": municipio.nome,
            "uf": municipio.uf,
            "codigo_ibge": municipio.codigo_ibge,
            "centroide": {"lat": centroide.y, "lon": centroide.x},
        },
    }
    return JsonResponse(feature)


def municipio_por_ponto(request):
    """
    GET /api/municipio-por-ponto/?lat=-15.6&lon=-56.1 — qual município de
    MT contém (ou toca) o ponto clicado no mapa. Point-in-polygon nativo
    do PostGIS (`geom__intersects` → `ST_Intersects` no SQL, roda no
    banco, não carrega geometria pro Python).

    `intersects` em vez de `contains` de propósito: em clique/toque de
    usuário perto de uma divisa entre municípios, `contains` (que exclui
    a borda exata) daria falso-negativo com frequência incômoda no
    celular. Com `intersects`, um clique bem em cima da linha entre dois
    municípios sempre casa com algum dos dois via `.first()` — aceitável,
    robustez de uso real importa mais aqui do que a exclusão teórica da
    borda.

    `null` se o ponto cair fora de MT (ou não for um município nenhum) —
    o frontend trata isso como "clique fora do escopo", não erro.
    """
    try:
        lat = float(request.GET.get("lat"))
        lon = float(request.GET.get("lon"))
    except (TypeError, ValueError):
        return JsonResponse({"erro": "Parâmetros 'lat' e 'lon' (numéricos) são obrigatórios."}, status=400)

    ponto = Point(lon, lat, srid=4326)  # GEOS Point é (x, y) = (longitude, latitude)
    municipio = Municipio.objects.filter(uf="MT", geom__intersects=ponto).first()

    if municipio is None:
        return JsonResponse(None, safe=False)

    return JsonResponse({
        "id": municipio.id,
        "nome": municipio.nome,
        "uf": municipio.uf,
        "codigo_ibge": municipio.codigo_ibge,
    })


def municipio_indicadores(request, municipio_id):
    """
    GET /api/municipios/<id>/indicadores/ — indicadores climáticos da
    FASE 1 (climate/municipio_indicators.py) pra home pública. Só expõe
    o que o módulo já calcula (cache incluso) — nenhuma conta nova
    acontece aqui.

    Município sem CHIRPS suficiente (fora de MT hoje, ou histórico
    curto demais) não é erro: cada campo vem `null`/vazio, resposta
    sempre 200 — quem decide como mostrar isso é o frontend.
    """
    municipio = get_object_or_404(Municipio, pk=municipio_id)

    spi = {}
    for escala, rotulo in ESCALAS_SPI_HOME:
        atual = mi.spi_atual(municipio, escala)
        spi[str(escala)] = {
            "rotulo": rotulo,
            "value": round(atual["value"], 2) if atual else None,
            "classification": atual["classification"] if atual else None,
            "date": atual["date"].isoformat() if atual else None,
        }

    anomalia = mi.anomalia_mensal(municipio)
    percentil = mi.percentil_historico_mensal(municipio)
    acumulados = mi.acumulados_municipio(municipio)

    return JsonResponse({
        "municipio": {
            "id": municipio.id,
            "nome": municipio.nome,
            "uf": municipio.uf,
            "codigo_ibge": municipio.codigo_ibge,
        },
        "spi": spi,
        "anomalia_mensal": anomalia,
        "percentil_historico": percentil,
        "climatologia_mensal": mi.climatologia_mensal(municipio),
        "acumulados": acumulados,
        "fonte": "CHIRPS",
    })


def municipio_spi_serie(request, municipio_id):
    """
    GET /api/municipios/<id>/spi-serie/?escala=3 — série temporal
    completa de SPI-<escala> do município (1981→hoje), pro gráfico de
    evolução da home pública. Repassa direto de
    municipio_indicators.spi_serie (já cacheado) — nenhum cálculo
    novo aqui. Filtro de período (5/10 anos/tudo) fica no frontend: a
    série inteira já é pequena (no máximo ~536 pontos mensais) e já
    vem cacheada, não vale a pena duplicar lógica de recorte no
    backend só pra isso.
    """
    municipio = get_object_or_404(Municipio, pk=municipio_id)

    try:
        escala = int(request.GET.get("escala", 3))
    except ValueError:
        escala = None
    if escala not in mi.ESCALAS_SPI:
        return JsonResponse(
            {"erro": f"Parâmetro 'escala' deve ser um de {mi.ESCALAS_SPI}."},
            status=400,
        )

    serie = mi.spi_serie(municipio, escala)
    return JsonResponse({
        "municipio": {"id": municipio.id, "nome": municipio.nome, "uf": municipio.uf},
        "escala": escala,
        "serie": [
            {
                "date": ponto["date"].isoformat(),
                "value": round(ponto["value"], 2),
                "classification": ponto["classification"],
            }
            for ponto in serie
        ],
    })


def _formatar_veranico(sub):
    if sub is None:
        return None
    return {
        "dias": sub["dias"],
        "inicio": sub["inicio"].isoformat() if sub["inicio"] else None,
        "fim": sub["fim"].isoformat() if sub["fim"] else None,
    }


def _formatar_recorde_mes(sub):
    return {"date": sub["date"].isoformat(), "total_mm": sub["total_mm"]}


def municipio_indicadores_fase2(request, municipio_id):
    """
    GET /api/municipios/<id>/indicadores-fase2/ — veranico, dias
    chuvosos, intensidade, recordes e tendência (Mann-Kendall + Sen's
    slope) do município, pra home pública. Mesmo padrão dos demais
    endpoints de município: só serializa o que
    climate.municipio_indicators já calcula (cache incluso), sem
    recalcular nada aqui. Município sem CHIRPS suficiente devolve
    campos `null`, sempre 200 — nunca 500.
    """
    municipio = get_object_or_404(Municipio, pk=municipio_id)

    veranico = mi.veranico(municipio)
    recordes = mi.recordes(municipio)
    tendencia = mi.tendencia_mann_kendall(municipio)

    return JsonResponse({
        "municipio": {"id": municipio.id, "nome": municipio.nome, "uf": municipio.uf},
        "veranico": {
            "recente_12_meses": _formatar_veranico(veranico["recente_12_meses"]) if veranico else None,
            "recorde_historico": _formatar_veranico(veranico["recorde_historico"]) if veranico else None,
        } if veranico else None,
        "dias_chuvosos": mi.dias_chuvosos(municipio),
        "intensidade_chuva": mi.intensidade_chuva(municipio),
        "recordes": {
            "ano_mais_chuvoso": recordes["ano_mais_chuvoso"],
            "ano_mais_seco": recordes["ano_mais_seco"],
            "mes_mais_chuvoso": _formatar_recorde_mes(recordes["mes_mais_chuvoso"]),
            "mes_mais_seco": _formatar_recorde_mes(recordes["mes_mais_seco"]),
            "n_anos_historico": recordes["n_anos_historico"],
        } if recordes else None,
        "tendencia": tendencia,
        "fonte": "CHIRPS",
    })


def municipio_series_anuais(request, municipio_id):
    """
    GET /api/municipios/<id>/series-anuais/ — evolução ANO A ANO
    (1981→ano completo mais recente) de dias chuvosos, intensidade e
    veranico máximo, pros gráficos "ver evolução" da home pública.
    Endpoint separado e buscado SOB DEMANDA (só quando o usuário clica
    em "ver evolução" pela primeira vez) — mesmo padrão de
    spi-serie/, não entra no payload inicial de indicadores-fase2/
    porque as 3 séries juntas são maiores e só uma minoria de visitantes
    vai abrir os gráficos. Município sem CHIRPS devolve `null`, 200.
    """
    municipio = get_object_or_404(Municipio, pk=municipio_id)

    dias_chuvosos_serie = mi.dias_chuvosos_serie_anual(municipio)
    intensidade_serie = mi.intensidade_serie_anual(municipio)
    veranico_serie = mi.veranico_maximo_serie_anual(municipio)

    return JsonResponse({
        "municipio": {"id": municipio.id, "nome": municipio.nome, "uf": municipio.uf},
        "dias_chuvosos": dias_chuvosos_serie,
        "intensidade": intensidade_serie,
        "veranico_maximo": (
            {
                "serie": {ano: _formatar_veranico(sub) for ano, sub in veranico_serie["serie"].items()},
                "tendencia": veranico_serie["tendencia"],
            }
            if veranico_serie else None
        ),
        "fonte": "CHIRPS",
    })


def municipio_exportar(request, municipio_id):
    """
    GET /api/municipios/<id>/exportar/ — devolve um .xlsx com os
    indicadores climáticos completos do município (público, sem
    login), pra pesquisadores/gestores reusarem o dado fora da
    plataforma. Mesma técnica de farms/views.py (Etapa 11):
    `workbook.save(resposta)` direto num HttpResponse com
    Content-Disposition, sem lib de arquivo extra.

    Município sem nenhum CHIRPS importado devolve 404 em texto simples
    — nunca gera um .xlsx vazio/quebrado.
    """
    municipio = get_object_or_404(Municipio, pk=municipio_id)

    if not ChirpsData.objects.filter(municipio=municipio).exists():
        return HttpResponse(
            f"Não há dados CHIRPS disponíveis para {municipio.nome}/{municipio.uf} ainda.",
            status=404,
            content_type="text/plain; charset=utf-8",
        )

    workbook = gerar_workbook_municipio(municipio)

    nome_arquivo = f"CHIRPS_{slugify(municipio.nome)}_{municipio.uf}_{timezone.localdate().strftime('%Y%m%d')}.xlsx"
    resposta = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    resposta["Content-Disposition"] = f'attachment; filename="{nome_arquivo}"'
    workbook.save(resposta)
    return resposta
