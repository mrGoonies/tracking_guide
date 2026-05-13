from django import forms

class ImportClientCSVForm(forms.Form):
    """Formulario para cargar archivo CSV de clientes."""
    csv_file = forms.FileField(
        label='Archivo CSV',
        help_text='Formato esperado: Cuenta de cliente; Dirección; Nombre',
        widget=forms.FileInput(attrs={'accept': '.csv'})
    )
