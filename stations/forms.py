# stations/forms.py
from django import forms
from django.contrib.gis.geos import Point

from farms.models import Farm
from .models import Station


class StationForm(forms.ModelForm):
    """
    Cadastro/edição de estação. O queryset de `farm` é restrito às
    fazendas do usuário logado (isolamento multiusuário) — por isso o
    form exige `user` no construtor, não dá pra usar sem passar isso.
    """

    class Meta:
        model = Station
        fields = ["name", "station_type", "farm", "latitude", "longitude"]
        labels = {
            "name": "Nome da Estação",
            "station_type": "Tipo",
            "farm": "Fazenda",
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is None:
            raise ValueError("StationForm precisa receber user= para restringir as fazendas do dono.")
        self.fields["farm"].queryset = Farm.objects.filter(owner=user)

        for nome_campo, campo in self.fields.items():
            if nome_campo in ("latitude", "longitude"):
                campo.widget.attrs["class"] = "form-control d-none"
            elif isinstance(campo.widget, forms.Select):
                campo.widget.attrs["class"] = "form-select"
            else:
                campo.widget.attrs["class"] = "form-control"

    def save(self, commit=True):
        estacao = super().save(commit=False)
        estacao.geom = Point(self.cleaned_data["longitude"], self.cleaned_data["latitude"], srid=4326)
        if commit:
            estacao.save()
        return estacao
