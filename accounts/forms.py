from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import User


class StyledFormMixin:
    """Ajoute la classe CSS 'form-control' à tous les champs.

    On l'écrit une seule fois (DRY) au lieu de le répéter dans chaque formulaire.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class RegisterForm(StyledFormMixin, UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "first_name", "last_name")


class LoginForm(StyledFormMixin, AuthenticationForm):
    pass


class ProfileForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email")