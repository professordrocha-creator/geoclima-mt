# climate/forms.py
from django import forms

from stations.models import Station
from .models import RainfallData


class LancamentoManualForm(forms.ModelForm):
    """
    Lançamento manual de chuva (Etapa 6, PDF: "chuva diária; horário;
    observações; anotações de campo"). O queryset de `station` é
    restrito às estações do usuário logado — exige `user=` no
    construtor, mesmo padrão do StationForm.
    """

    class Meta:
        model = RainfallData
        fields = ["station", "date", "time", "value", "notes"]
        widgets = {
            # format="..." força AAAA-MM-DD/HH:MM (exigido pelo <input type=date/time>
            # do HTML5) mesmo com LANGUAGE_CODE=pt-br — sem isso, o Django preenche
            # o value no formato localizado (DD/MM/AAAA), o navegador rejeita
            # silenciosamente, e o campo fica vazio ao editar um lançamento existente.
            "date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "station": "Estação/Pluviômetro",
            "date": "Data",
            "time": "Horário (opcional)",
            "value": "Chuva (mm)",
            "notes": "Observações / anotações de campo",
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is None:
            raise ValueError("LancamentoManualForm precisa receber user= para restringir as estações do dono.")
        self.fields["station"].queryset = Station.objects.filter(owner=user).select_related("farm")

        for nome_campo, campo in self.fields.items():
            if isinstance(campo.widget, forms.Select):
                campo.widget.attrs["class"] = "form-select"
            else:
                campo.widget.attrs["class"] = "form-control"

    def clean_value(self):
        # Bloqueia chuva negativa já na entrada manual (Etapa 7.3) — pega
        # o erro de digitação na hora, em vez de só detectar depois via
        # climate/quality_checks.py (que continua rodando sobre CSV
        # importado, que não passa por este form).
        valor = self.cleaned_data["value"]
        if valor < 0:
            raise forms.ValidationError("Chuva não pode ser negativa.")
        return valor

    def save(self, commit=True):
        # source_type='manual' é o default do model — lançamento manual
        # nunca precisa (nem deve) escolher outra origem.
        lancamento = super().save(commit=False)
        lancamento.source_type = "manual"
        if commit:
            lancamento.save()
        return lancamento


class ImportacaoArquivoForm(forms.Form):
    """Upload de CSV/Excel de precipitação (Etapa 6) para uma estação já cadastrada."""

    station = forms.ModelChoiceField(
        queryset=Station.objects.none(), label="Estação/Pluviômetro",
        help_text="Todos os registros do arquivo serão gravados nesta estação.",
    )
    arquivo = forms.FileField(
        label="Arquivo (.csv ou .xlsx)",
        help_text="Precisa ter colunas de data e valor (mm). Horário e observações são opcionais.",
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is None:
            raise ValueError("ImportacaoArquivoForm precisa receber user= para restringir as estações do dono.")
        self.fields["station"].queryset = Station.objects.filter(owner=user).select_related("farm")
        self.fields["station"].widget.attrs["class"] = "form-select"
        self.fields["arquivo"].widget.attrs["class"] = "form-control"
        self.fields["arquivo"].widget.attrs["accept"] = ".csv,.xlsx"

    def clean_arquivo(self):
        arquivo = self.cleaned_data["arquivo"]
        if not arquivo.name.lower().endswith((".csv", ".xlsx")):
            raise forms.ValidationError("Envie um arquivo .csv ou .xlsx.")
        return arquivo
