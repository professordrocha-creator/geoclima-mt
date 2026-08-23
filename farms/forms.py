# farms/forms.py
from django import forms
from django.contrib.gis.geos import Point

from .models import Farm, Talhao


class FarmForm(forms.ModelForm):
    """
    Cadastro/edição de fazenda. O campo `municipio` é um ModelChoiceField
    normal para fins de validação (aceita qualquer um dos 5.573
    municípios do Brasil), mas o <select> em si é populado via JS pelo
    mesmo seletor Estado→Cidade da Home (/api/estados/, /api/municipios/)
    — não renderizamos um <select> gigante com todos os municípios de
    uma vez. `latitude`/`longitude` vêm de um clique no mapa Leaflet do
    template, sincronizados via JS; `geom` é calculado a partir deles no
    save(), não é campo do form.

    `shapefile` é opcional e NÃO é campo do model — a view
    (farms/views.py) lê `request.FILES['shapefile']` diretamente e chama
    farms/shapefile_import.py. Se um shapefile com polígono for enviado,
    ele manda mais que o clique no mapa (a localização vira o centroide
    do polígono importado) — por isso latitude/longitude são opcionais
    aqui no form; a obrigatoriedade de "ter uma localização de algum
    jeito" (mapa OU shapefile) é checada na view, depois de tentar
    processar o shapefile.
    """

    shapefile = forms.FileField(
        required=False,
        label="Importar Shapefile (.zip com .shp/.shx/.dbf/.prj)",
        help_text=(
            "Opcional. Polígonos no arquivo viram o contorno da fazenda; "
            "pontos viram estações automaticamente. Sem shapefile, use o "
            "mapa abaixo normalmente."
        ),
    )

    class Meta:
        model = Farm
        fields = ["name", "municipio", "latitude", "longitude", "area", "crop", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "name": "Nome da Fazenda",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Opcionais no form: podem vir do clique no mapa OU do shapefile
        # (a view decide, depois de tentar processar o arquivo enviado).
        self.fields["latitude"].required = False
        self.fields["longitude"].required = False

        for nome_campo, campo in self.fields.items():
            if nome_campo in ("latitude", "longitude", "municipio"):
                campo.widget.attrs["class"] = "form-control d-none"
            elif nome_campo == "shapefile":
                campo.widget.attrs["class"] = "form-control"
                campo.widget.attrs["accept"] = ".zip"
            else:
                campo.widget.attrs["class"] = "form-control"

    def save(self, commit=True):
        fazenda = super().save(commit=False)
        lat = self.cleaned_data.get("latitude")
        lon = self.cleaned_data.get("longitude")
        if lat is not None and lon is not None:
            fazenda.geom = Point(lon, lat, srid=4326)
        # Se lat/lon vieram vazios (fluxo só-shapefile), a view preenche
        # fazenda.geom/latitude/longitude a partir do polígono importado
        # antes de chamar fazenda.save() de verdade.
        if commit:
            fazenda.save()
        return fazenda


class TalhaoForm(forms.ModelForm):
    """
    Cadastro/edição de talhão dentro de uma fazenda. `farm`/`owner` são
    definidos na view (a partir da fazenda já validada como do próprio
    usuário), não aparecem no form.
    """

    class Meta:
        model = Talhao
        fields = ["name", "latitude", "longitude", "area", "crop"]
        labels = {
            "name": "Nome do Talhão",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nome_campo, campo in self.fields.items():
            if nome_campo in ("latitude", "longitude"):
                campo.widget.attrs["class"] = "form-control d-none"
            else:
                campo.widget.attrs["class"] = "form-control"

    def save(self, commit=True):
        talhao = super().save(commit=False)
        talhao.geom = Point(self.cleaned_data["longitude"], self.cleaned_data["latitude"], srid=4326)
        if commit:
            talhao.save()
        return talhao
