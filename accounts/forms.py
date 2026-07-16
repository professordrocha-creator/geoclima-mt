# accounts/forms.py
from django import forms
from django.contrib.auth.forms import SetPasswordForm, UserCreationForm
from django.contrib.auth.models import User


class CadastroForm(UserCreationForm):
    """
    Formulário de registro público. Propositalmente NÃO tem campo de
    papel/perfil — o Profile é criado à parte pelo signal
    (accounts/signals.py) sempre com profile_type="produtor". Assim, é
    impossível um usuário público escolher "administrador" no cadastro,
    porque o campo nem existe no formulário.
    """
    email = forms.EmailField(required=True, label="E-mail")

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # UserCreationForm não usa classes Bootstrap por padrão — aplicamos aqui.
        for campo in self.fields.values():
            campo.widget.attrs["class"] = "form-control"

    def clean_email(self):
        email = self.cleaned_data["email"]
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Já existe uma conta cadastrada com este e-mail.")
        return email

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.email = self.cleaned_data["email"]
        if commit:
            usuario.save()
        return usuario


class NovaSenhaForm(SetPasswordForm):
    """SetPasswordForm padrão do Django, só com classe Bootstrap nos campos."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            campo.widget.attrs["class"] = "form-control"
