from datetime import timedelta, datetime
from io import BytesIO

from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from openpyxl import Workbook
from .decorators import admin_or_coordinador_required
from .forms import CreateDispatchGuideForm, UpdateGuideStateForm
from .utils import get_home_url_for_user, is_transportista, is_coordinador
from .models import Client, DispatchGuide, GuideStage

def home(request):
    if request.user.is_authenticated:
        return redirect(get_home_url_for_user(request.user))
    return redirect('login')


@admin_or_coordinador_required
def hub(request):
    resumen = {
        'total_guias': DispatchGuide.objects.count(),
        'en_ruta': DispatchGuide.objects.filter(estado='en_ruta').count(),
        'pendientes': DispatchGuide.objects.filter(estado__in=['emitida', 'asignada']).count(),
        'entregadas_hoy': DispatchGuide.objects.filter(
            estado='entregada',
            fecha_actualizacion__date=timezone.localdate()
        ).count(),
    }
    return render(request, 'guides/hub.html', {'resumen': resumen})


def user_login(request):
    if request.user.is_authenticated:
        return redirect('guide_list')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect(request.GET.get('next') or get_home_url_for_user(user))
    else:
        form = AuthenticationForm()

    return render(request, 'guides/login.html', {'form': form})


@login_required
def user_logout(request):
    logout(request)
    messages.success(request, 'Sesión cerrada correctamente')
    return redirect('home')



@admin_or_coordinador_required
def guide_list(request):
    estado_filtro = request.GET.get('estado', '').strip()
    guides = DispatchGuide.objects.select_related('cliente', 'transportista', 'vendedor').order_by('-fecha_creacion')
    
    if estado_filtro:
        guides = guides.filter(estado=estado_filtro)
    
    context = {
        'guides': guides,
        'estado_filtro': estado_filtro,
        'estado_choices': DispatchGuide.STATUS_CHOICES,
    }
    return render(request, 'guides/guide_list.html', context)


@admin_or_coordinador_required
def export_route_planning(request):
    """Exporta un archivo Excel con la planificación de rutas."""
    guides = DispatchGuide.objects.select_related('cliente', 'transportista', 'vendedor').order_by('fecha_creacion')

    # Aplicar filtro por rango de fechas (fecha_envio)
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    try:
        if start_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            guides = guides.filter(fecha_envio__gte=start_date)
        if end_date_str:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
            guides = guides.filter(fecha_envio__lte=end_date)
    except ValueError:
        # Ignorar filtros mal formateados
        pass

    wb = Workbook()
    ws = wb.active
    ws.title = 'Planificación Rutas'
    headers = [
        'Nota de Venta (NV)',
        'Creacion de la NV',
        'Fecha de Envio',
        'Rut Cliente',
        'Nombre cliente',
        'Direccion de despacho',
        'Persona que creo la NV',
        'Transportista asignado para esa nota de venta',
        'Fecha de despacho',
        'Numero de guia'
    ]
    ws.append(headers)

    for guide in guides:
        vendedor_nombre = guide.vendedor_nombre or (guide.vendedor.nombre if guide.vendedor else '')
        transportista_nombre = guide.transportista.get_full_name() if guide.transportista else ''
        ws.append([
            guide.nv or '',
            guide.nv_fecha_creacion or '',
            guide.fecha_envio or '',
            guide.cliente.rut,
            guide.cliente.nombre,
            guide.direccion_entrega,
            vendedor_nombre,
            transportista_nombre,
            guide.fecha_despacho or '',
            guide.numero_guia,
        ])

    for i, _ in enumerate(headers, start=1):
        column_letter = ws.cell(row=1, column=i).column_letter
        max_length = max(
            len(str(cell.value)) if cell.value is not None else 0
            for cell in ws[column_letter]
        )
        ws.column_dimensions[column_letter].width = min(max_length + 4, 40)

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename=planificacion_rutas.xlsx'
    return response


@admin_or_coordinador_required
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


@login_required
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


@admin_or_coordinador_required
def create_guide(request):
    """Vista para crear una nueva guía de despacho (mobile-first)."""
    admin_session = request.user.is_staff or is_coordinador(request.user)

    if request.method == 'POST':
        form = CreateDispatchGuideForm(request.POST, request.FILES, admin_session=admin_session)

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
                foto=form.cleaned_data.get('foto_emision'),
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
def transportista_guides(request):
    """Vista mobile-first para que el transportista vea sus guías asignadas."""
    if not is_transportista(request.user) and not request.user.is_staff:
        return redirect('guide_list')

    filtro = request.GET.get('filtro', 'activas')
    guides = DispatchGuide.objects.filter(
        transportista=request.user
    ).select_related('cliente').order_by('fecha_despacho', '-fecha_creacion')

    if filtro == 'activas':
        guides = guides.filter(estado__in=['emitida', 'asignada', 'en_ruta'])
    else:
        guides = guides.filter(estado__in=['entregada', 'rechazada', 'cerrada'])

    context = {
        'guides': guides,
        'filtro': filtro,
    }
    return render(request, 'guides/transportista_guides.html', context)


@login_required
def guide_detail(request, guide_id):
    """Vista para ver y actualizar el estado de una guía específica."""
    try:
        guide = DispatchGuide.objects.get(id=guide_id)
    except DispatchGuide.DoesNotExist:
        messages.error(request, 'Guía no encontrada')
        return redirect(get_home_url_for_user(request.user))

    # Transportista solo puede acceder a sus propias guías
    if is_transportista(request.user) and guide.transportista != request.user:
        messages.error(request, 'No tienes acceso a esta guía.')
        return redirect('transportista_guides')
    
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
            evidencia_foto = form.cleaned_data.get('evidencia_foto')
            notas = form.cleaned_data.get('notas', '')

            if nuevo_estado in ('entregada', 'rechazada') and not evidencia_foto:
                form.add_error('evidencia_foto', 'La foto es obligatoria al marcar como entregada o rechazada.')
            else:
                GuideStage.objects.create(
                    guia=guide,
                    estado=nuevo_estado,
                    foto=evidencia_foto,
                    observaciones=notas
                )

                guide.estado = nuevo_estado
                if nuevo_estado in ['entregada', 'rechazada'] and not guide.fecha_envio:
                    guide.fecha_envio = timezone.localdate()
                guide.save()

                messages.success(request, f'✓ Estado actualizado a "{guide.get_estado_display()}"')
                return redirect('guide_detail', guide_id=guide.id)
    else:
        form = UpdateGuideStateForm()
    
    template = (
        'guides/transportista_guide_detail.html'
        if is_transportista(request.user)
        else 'guides/guide_detail.html'
    )
    back_url = 'transportista_guides' if is_transportista(request.user) else 'guide_list'

    context = {
        'guide': guide,
        'stages': stages,
        'form': form,
        'next_states': next_states,
        'back_url': back_url,
    }
    return render(request, template, context)
