from django import forms
from django.contrib.auth.models import User
from django.db.models import Q
from .models import Client, DispatchGuide, Seller

class ImportClientCSVForm(forms.Form):
    """Formulario para cargar archivo CSV de clientes."""
    csv_file = forms.FileField(
        label='Archivo CSV',
        help_text='Formato esperado: Cuenta de cliente; Dirección; Nombre',
        widget=forms.FileInput(attrs={'accept': '.csv'})
    )


class CreateDispatchGuideForm(forms.ModelForm):
    """Formulario para crear una nueva guía de despacho."""
    rut = forms.CharField(
        label='RUT del Cliente',
        max_length=20,
        widget=forms.TextInput(attrs={
            'placeholder': 'Ej: 12345678-9',
            'autocomplete': 'off',
            'class': 'form-input'
        })
    )
    
    usa_direccion_facturacion = forms.BooleanField(
        label='Usar dirección de facturación',
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-checkbox'})
    )
    
    vendedor = forms.ModelChoiceField(
        queryset=Seller.objects.filter(activo=True),
        label='Vendedor / Asistente Comercial',
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    vendedor_nombre = forms.CharField(
        label='Nombre manual del vendedor / asistente',
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Nombre completo',
            'class': 'form-input'
        })
    )
    
    class Meta:
        model = DispatchGuide
        fields = ['numero_guia', 'transportista', 'vendedor', 'vendedor_nombre', 'notas']
        widgets = {
            'numero_guia': forms.TextInput(attrs={
                'placeholder': 'Número único de la guía',
                'class': 'form-input'
            }),
            'transportista': forms.Select(attrs={
                'class': 'form-select'
            }),
            'notas': forms.Textarea(attrs={
                'placeholder': 'Observaciones adicionales',
                'rows': 3,
                'class': 'form-textarea'
            })
        }

    def __init__(self, *args, admin_session=False, **kwargs):
        super().__init__(*args, **kwargs)
        transportistas = User.objects.filter(groups__name='Transportista')
        if transportistas.exists():
            self.fields['transportista'].queryset = transportistas
        else:
            self.fields['transportista'].queryset = User.objects.all()

        # Vendedor ahora usa Seller, no necesita filtrado adicional aquí
        if not admin_session:
            self.fields['vendedor_nombre'].widget = forms.HiddenInput()


class UpdateGuideStateForm(forms.Form):
    """Formulario para actualizar el estado de una guía con evidencia fotográfica."""
    nuevo_estado = forms.ChoiceField(
        label='Nuevo Estado',
        choices=DispatchGuide.STATUS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    evidencia_foto = forms.ImageField(
        label='Evidencia Fotográfica',
        required=True,
        widget=forms.FileInput(attrs={'accept': 'image/*', 'capture': 'environment', 'class': 'form-input'})
    )
    
    notas = forms.CharField(
        label='Notas del Cambio',
        required=False,
        widget=forms.Textarea(attrs={
            'placeholder': 'Observaciones sobre el cambio de estado',
            'rows': 2,
            'class': 'form-textarea'
        })
    )
