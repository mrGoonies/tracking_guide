from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import ImportClientCSVForm
from .utils import import_clients_from_csv
from .models import Client

def home(request):
    return render(request, 'guides/home.html')

def import_clients(request):
    """Vista para importar clientes desde CSV."""
    if request.method == 'POST':
        form = ImportClientCSVForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = request.FILES['csv_file']
            
            # Importar clientes
            results = import_clients_from_csv(csv_file)
            
            # Mostrar mensajes según resultados
            if results['success'] > 0:
                messages.success(request, f"✓ {results['success']} cliente(s) nuevo(s) importado(s)")
            if results['updated'] > 0:
                messages.info(request, f"ℹ {results['updated']} cliente(s) actualizado(s)")
            if results['errors']:
                for error in results['errors']:
                    messages.error(request, f"✗ {error}")
            
            # Mostrar resumen
            if not results['errors']:
                messages.success(request, f"Importación completada: {results['total']} registros procesados")
            
            # Redirigir para evitar reenvío de formulario
            return redirect('import_clients')
    else:
        form = ImportClientCSVForm()
    
    # Mostrar estadísticas de clientes
    total_clients = Client.objects.count()
    context = {
        'form': form,
        'total_clients': total_clients
    }
    return render(request, 'guides/import_clients.html', context)

def guide_list(request):
    return render(request, 'guides/guide_list.html')
