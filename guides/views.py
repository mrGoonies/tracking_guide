from datetime import timedelta

from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from .forms import ImportClientCSVForm, CreateDispatchGuideForm, UpdateGuideStateForm
from .utils import import_clients_from_csv
from .models import Client, DispatchGuide, GuideStage

def home(request):
    return render(request, 'guides/home.html')


def user_login(request):
    if request.user.is_authenticated:
        return redirect('guide_list')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            return redirect(request.GET.get('next') or 'guide_list')
    else:
        form = AuthenticationForm()

    return render(request, 'guides/login.html', {'form': form})


@login_required
def user_logout(request):
    logout(request)
    messages.success(request, 'Sesión cerrada correctamente')
    return redirect('home')


@login_required
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

@login_required
def guide_list(request):
    estado_filtro = request.GET.get('estado', '').strip()
    guides = DispatchGuide.objects.select_related('cliente', 'transportista').order_by('-fecha_creacion')
    
    if estado_filtro:
        guides = guides.filter(estado=estado_filtro)
    
    context = {
        'guides': guides,
        'estado_filtro': estado_filtro,
        'estado_choices': DispatchGuide.STATUS_CHOICES,
    }
    return render(request, 'guides/guide_list.html', context)


@login_required
def dashboard(request):
    total_clients = Client.objects.count()
    total_guides = DispatchGuide.objects.count()
    total_stages = GuideStage.objects.count()
    status_counts = {status: 0 for status, _ in DispatchGuide.STATUS_CHOICES}
    for item in DispatchGuide.objects.values('estado').annotate(count=Count('id')):
        status_counts[item['estado']] = item['count']

    status_breakdown = []
    for status, label in DispatchGuide.STATUS_CHOICES:
        count = status_counts.get(status, 0)
        percent = (count / total_guides * 100) if total_guides else 0
        status_breakdown.append({
            'estado': status,
            'label': label,
            'count': count,
            'percent': round(percent, 1)
        })

    open_guides = DispatchGuide.objects.filter(~Q(estado__in=['entregada', 'rechazada', 'cerrada'])).count()
    closed_guides = DispatchGuide.objects.filter(estado__in=['entregada', 'rechazada', 'cerrada']).count()
    recent_guides = DispatchGuide.objects.select_related('cliente', 'transportista').order_by('-fecha_creacion')[:8]
    week_start = timezone.now() - timedelta(days=7)
    guides_last_7_days = DispatchGuide.objects.filter(fecha_creacion__gte=week_start).count()
    top_clients = Client.objects.annotate(guides_count=Count('guias')).order_by('-guides_count')[:5]
    top_carriers = User.objects.annotate(guides_count=Count('guias_asignadas')).filter(guides_count__gt=0).order_by('-guides_count')[:5]
    latest_stages = GuideStage.objects.select_related('guia').order_by('-timestamp')[:8]
    stage_photo_count = GuideStage.objects.filter(foto__isnull=False).count()

    context = {
        'total_clients': total_clients,
        'total_guides': total_guides,
        'total_stages': total_stages,
        'status_breakdown': status_breakdown,
        'open_guides': open_guides,
        'closed_guides': closed_guides,
        'recent_guides': recent_guides,
        'guides_last_7_days': guides_last_7_days,
        'top_clients': top_clients,
        'top_carriers': top_carriers,
        'latest_stages': latest_stages,
        'stage_photo_count': stage_photo_count,
    }
    return render(request, 'guides/dashboard.html', context)


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


@login_required
def create_guide(request):
    """Vista para crear una nueva guía de despacho (mobile-first)."""
    admin_session = request.user.is_staff

    if request.method == 'POST':
        form = CreateDispatchGuideForm(request.POST, admin_session=admin_session)
        
        rut = request.POST.get('rut', '').strip()
        direccion_entrega = request.POST.get('direccion_entrega', '').strip()
        usa_direccion_facturacion = request.POST.get('usa_direccion_facturacion') == 'on'
        map_link = request.POST.get('map_link', '').strip()
        
        if not rut:
            messages.error(request, 'Debe ingresar el RUT del cliente')
            return render(request, 'guides/create_guide.html', {'form': form, 'admin_session': admin_session})

        try:
            cliente = Client.objects.get(rut=rut)
        except Client.DoesNotExist:
            messages.error(request, f'No existe cliente con RUT: {rut}')
            return render(request, 'guides/create_guide.html', {'form': form, 'admin_session': admin_session})
        
        if form.is_valid():
            if not usa_direccion_facturacion and not direccion_entrega:
                messages.error(request, 'Debe ingresar una dirección de entrega si no usa la de facturación')
                return render(request, 'guides/create_guide.html', {'form': form, 'admin_session': admin_session})
            
            guide = form.save(commit=False)
            guide.cliente = cliente
            
            if usa_direccion_facturacion:
                guide.direccion_entrega = cliente.direccion_facturacion
            else:
                guide.direccion_entrega = direccion_entrega
            
            if map_link:
                guide.map_link = map_link
            
            if not admin_session:
                guide.vendedor_nombre = None
            guide.usa_direccion_facturacion = usa_direccion_facturacion
            guide.save()
            
            GuideStage.objects.create(
                guia=guide,
                estado='emitida',
                observaciones='Guía emitida en el sistema'
            )
            
            messages.success(request, f'✓ Guía {guide.numero_guia} creada exitosamente')
            return redirect('guide_list')
    else:
        form = CreateDispatchGuideForm(admin_session=admin_session)
    
    context = {
        'form': form,
        'admin_session': admin_session,
    }
    return render(request, 'guides/create_guide.html', context)


@login_required
def guide_detail(request, guide_id):
    """Vista para ver y actualizar el estado de una guía específica."""
    try:
        guide = DispatchGuide.objects.get(id=guide_id)
    except DispatchGuide.DoesNotExist:
        messages.error(request, 'Guía no encontrada')
        return redirect('guide_list')
    
    stages = guide.etapas.order_by('-timestamp')
    
    next_state_map = {
        'emitida': [('asignada', 'Asignar'), ('en_ruta', 'En Ruta'), ('rechazada', 'Rechazada')],
        'asignada': [('en_ruta', 'En Ruta'), ('entregada', 'Entregada'), ('rechazada', 'Rechazada')],
        'en_ruta': [('entregada', 'Entregada'), ('rechazada', 'Rechazada')],
        'entregada': [('cerrada', 'Cerrar')],
        'rechazada': [('cerrada', 'Cerrar')],
        'cerrada': [],
    }
    next_states = next_state_map.get(guide.estado, [])
    
    if request.method == 'POST':
        form = UpdateGuideStateForm(request.POST, request.FILES)
        if form.is_valid():
            nuevo_estado = form.cleaned_data['nuevo_estado']
            evidencia_foto = form.cleaned_data['evidencia_foto']
            notas = form.cleaned_data.get('notas', '')
            
            GuideStage.objects.create(
                guia=guide,
                estado=nuevo_estado,
                evidencia_foto=evidencia_foto,
                observaciones=notas
            )
            
            guide.estado = nuevo_estado
            guide.save()
            
            messages.success(request, f'✓ Estado actualizado a "{guide.get_estado_display()}"')
            return redirect('guide_detail', guide_id=guide.id)
    else:
        form = UpdateGuideStateForm()
    
    context = {
        'guide': guide,
        'stages': stages,
        'form': form,
        'next_states': next_states,
    }
    return render(request, 'guides/guide_detail.html', context)
