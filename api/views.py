# api/views.py
import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from maps.models import Municipio

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
