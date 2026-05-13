from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from .forms import ImportClientCSVForm, CreateDispatchGuideForm
from .utils import import_clients_from_csv
from .models import Client, DispatchGuide, GuideStage

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


@require_POST
def search_client_by_rut(request):
    """API endpoint para buscar cliente por RUT (AJAX)."""
    rut = request.POST.get('rut', '').strip()
    
    if not rut:
        return JsonResponse({'error': 'RUT requerido'}, status=400)
    
    try:
        client = Client.objects.get(rut=rut)
        return JsonResponse({
            'success': True,
            'rut': client.rut,
            'nombre': client.nombre,
            'direccion_facturacion': client.direccion_facturacion,
            'direccion_entrega_preferida': client.direccion_entrega_preferida or ''
        })
    except Client.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': f'No existe cliente con RUT: {rut}'
        }, status=404)


def create_guide(request):
    """Vista para crear una nueva guía de despacho (mobile-first)."""
    if request.method == 'POST':
        form = CreateDispatchGuideForm(request.POST)
        
        # Obtener datos de dirección entrega si no usa facturación
        direccion_entrega = request.POST.get('direccion_entrega', '').strip()
        usa_direccion_facturacion = request.POST.get('usa_direccion_facturacion') == 'on'
        map_link = request.POST.get('map_link', '').strip()
        
        if form.is_valid():
            # Validar que si no usa dirección de facturación, ingrese una alternativa
            if not usa_direccion_facturacion and not direccion_entrega:
                messages.error(request, 'Debe ingresar una dirección de entrega si no usa la de facturación')
                return render(request, 'guides/create_guide.html', {'form': form})
            
            guide = form.save(commit=False)
            
            # Asignar dirección de entrega custom si aplica
            if not usa_direccion_facturacion:
                guide.direccion_entrega = direccion_entrega
            
            # Asignar map_link si existe
            if map_link:
                guide.map_link = map_link
            
            guide.usa_direccion_facturacion = usa_direccion_facturacion
            guide.save()
            
            # Registrar la etapa inicial
            GuideStage.objects.create(
                guia=guide,
                estado='emitida',
                observaciones='Guía emitida en el sistema'
            )
            
            messages.success(request, f'✓ Guía {guide.numero_guia} creada exitosamente')
            return redirect('guide_list')
    else:
        form = CreateDispatchGuideForm()
    
    context = {
        'form': form
    }
    return render(request, 'guides/create_guide.html', context)
