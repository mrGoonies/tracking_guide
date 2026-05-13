from django import forms
from django.contrib.auth.models import User
from .models import Client, DispatchGuide

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
    
    class Meta:
        model = DispatchGuide
        fields = ['numero_guia', 'transportista', 'notas']
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
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filtrar transportistas: solo usuarios que puedan ser transportistas
        self.fields['transportista'].queryset = User.objects.all()
        self.fields['transportista'].required = False
    
    def clean(self):
        cleaned_data = super().clean()
        rut = cleaned_data.get('rut')
        
        # Validar que el cliente exista
        if rut:
            try:
                client = Client.objects.get(rut=rut.strip())
                cleaned_data['cliente'] = client
            except Client.DoesNotExist:
                raise forms.ValidationError(f"No existe cliente con RUT: {rut}")
        
        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.cliente = self.cleaned_data.get('cliente')
        
        # Asignar dirección de entrega
        if self.cleaned_data.get('usa_direccion_facturacion'):
            instance.direccion_entrega = instance.cliente.direccion_facturacion
        # Si no usa facturación, la dirección debe ser completada en otra vista
        
        if commit:
            instance.save()
        return instance
