from django import forms
from django.contrib.auth import get_user_model

from .models import (AccionSugerida, Alternativa, Dimension, Evaluacion, Factor, Perfil, Subfactor,
                     SECTORES, TAMANOS)

User = get_user_model()


class AlternativaForm(forms.ModelForm):
    class Meta:
        model = Alternativa
        fields = ["nombre", "descripcion"]
        widgets = {"nombre": forms.TextInput(attrs={"placeholder": "Ej. LibreOffice"}),
                   "descripcion": forms.Textarea(attrs={"rows": 3, "placeholder": "¿Qué software es y para qué se usaría?"})}


class EvaluacionForm(forms.Form):
    alternativa = forms.ModelChoiceField(Alternativa.objects.all(), empty_label="Elige una alternativa")
    sector = forms.ChoiceField(choices=SECTORES, label="Sector de la organización")
    tamano = forms.ChoiceField(choices=TAMANOS, label="Tamaño de la organización")
    usar_is_ia = forms.BooleanField(required=False, label="Usar la importancia sugerida ajustada por IA para este perfil")
    criterio = forms.ChoiceField(choices=Evaluacion.CRITERIOS, label="Criterio de consolidación", initial="PROMEDIO")
    invitados = forms.CharField(required=False, label="Invitar decisores (correos)",
                                widget=forms.Textarea(attrs={"rows": 2, "placeholder": "maria@unemi.edu.ec, luis@unemi.edu.ec"}))


class FactorForm(forms.ModelForm):
    class Meta:
        model = Factor
        fields = ["dimension", "nombre", "alcance", "importancia_sugerida"]

    def save(self, commit=True):
        obj = super().save(commit=False)
        if not obj.pk:
            obj.importancia_base = obj.importancia_sugerida
        if commit:
            obj.save()
        return obj


class SubfactorForm(forms.ModelForm):
    class Meta:
        model = Subfactor
        fields = ["factor", "texto"]
        widgets = {"texto": forms.Textarea(attrs={"rows": 2})}


class AccionForm(forms.ModelForm):
    class Meta:
        model = AccionSugerida
        fields = ["factor", "aplica_a", "descripcion"]
        widgets = {"descripcion": forms.Textarea(attrs={"rows": 2})}


class UsuarioForm(forms.Form):
    correo = forms.EmailField()
    nombre = forms.CharField(max_length=80)
    rol = forms.ChoiceField(choices=Perfil.ROLES)
    password = forms.CharField(min_length=8, widget=forms.PasswordInput, label="Contraseña temporal")

    def clean_correo(self):
        c = self.cleaned_data["correo"].lower()
        if User.objects.filter(username__iexact=c).exists():
            raise forms.ValidationError("Ya existe un usuario con ese correo.")
        return c
