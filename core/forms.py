# core/forms.py
from django import forms

from maps.models import Municipio


class CalculadoraValidacaoForm(forms.Form):
    """
    Formulário da calculadora de validação CHIRPS × pluviômetro (público,
    sem login). Só município `ativo=True` — mesmo princípio de todo o
    projeto: dado científico pesado (CHIRPS) só existe onde já foi
    importado, isso é limite de DADO, não de código (ver docs/DECISOES.md).
    """

    municipio = forms.ModelChoiceField(
        queryset=Municipio.objects.filter(ativo=True).order_by("uf", "nome"),
        label="Município (comparar com o CHIRPS deste município)",
        empty_label="Selecione o município",
    )
    arquivo = forms.FileField(
        label="Arquivo com a chuva medida (.csv ou .xlsx)",
        help_text="Precisa ter uma coluna de data e uma de valor (chuva em mm). Diário ou totais mensais — o sistema detecta automaticamente.",
    )
