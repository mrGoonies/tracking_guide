import io
import logging

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

logger = logging.getLogger(__name__)

from guides.models import DispatchGuide, GuideStage, GuideStagePhoto
from guides.services import send_seller_notification, send_coordinator_notification
from .permissions import IsTransportista
from .serializers import (
    CustomTokenObtainPairSerializer,
    DispatchGuideListSerializer,
    DispatchGuideDetailSerializer,
)

ESTADOS_REQUIEREN_FOTO = ('entregada', 'rechazada')


def _upload_guide_pdf(image_file, guide):
    """
    Converts the guide photo to PDF locally (Pillow) and uploads it to Cloudinary
    as a raw resource. Skipped in DEBUG mode. Returns the secure URL or None.
    """
    from django.conf import settings
    if settings.DEBUG:
        return None

    import cloudinary.uploader
    from PIL import Image
    from django.utils import timezone

    now = timezone.now()
    timestamp = now.strftime('%Y-%m-%d_%H%M')
    safe_guia = ''.join(c if c.isalnum() or c in '-_' else '_' for c in str(guide.numero_guia))
    public_id = (
        f"tracking/guide_pdfs/{now.year}/{now.month:02d}/{now.day:02d}/"
        f"{safe_guia}_{timestamp}.pdf"
    )

    try:
        image_file.seek(0)
        img = Image.open(image_file)
        if img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')
        pdf_buf = io.BytesIO()
        img.save(pdf_buf, format='PDF')
        pdf_buf.seek(0)

        result = cloudinary.uploader.upload(
            pdf_buf,
            resource_type='raw',
            public_id=public_id,
            overwrite=True,
        )
        return result.get('secure_url')
    except Exception as exc:
        logger.error('[PDF] Error generando PDF. guia=%s: %s', guide.numero_guia, exc, exc_info=True)
        return None


# Transportistas no pueden cerrar guías — solo admin/coordinador desde la web
ESTADOS_VALIDOS_TRANSPORTISTA = {'asignada', 'en_ruta', 'entregada', 'rechazada'}


# ── Auth ─────────────────────────────────────────────────────────────────────

class LoginView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


# ── Perfil del usuario autenticado ───────────────────────────────────────────

class MeView(APIView):
    permission_classes = [IsTransportista]

    def get(self, request):
        user = request.user
        return Response({
            'id':       user.id,
            'username': user.username,
            'nombre':   user.get_full_name() or user.username,
            'email':    user.email,
        })


# ── Guías del transportista ──────────────────────────────────────────────────

class MisGuiasView(generics.ListAPIView):
    serializer_class = DispatchGuideListSerializer
    permission_classes = [IsTransportista]

    def get_queryset(self):
        qs = DispatchGuide.objects.filter(
            transportista=self.request.user
        ).select_related('cliente').order_by('fecha_despacho', '-fecha_creacion')

        # Filtro opcional por estado (?estado=en_ruta)
        estado = self.request.query_params.get('estado')
        if estado:
            qs = qs.filter(estado=estado)

        return qs


# ── Detalle de una guía ───────────────────────────────────────────────────────

class GuiaDetailView(generics.RetrieveAPIView):
    serializer_class = DispatchGuideDetailSerializer
    permission_classes = [IsTransportista]

    def get_queryset(self):
        return DispatchGuide.objects.filter(
            transportista=self.request.user
        ).select_related('cliente').prefetch_related(
            'etapas__fotos'
        )


# ── Actualizar estado de una guía ─────────────────────────────────────────────

class UpdateEstadoView(APIView):
    permission_classes = [IsTransportista]

    def post(self, request, pk):
        guide = get_object_or_404(
            DispatchGuide, id=pk, transportista=request.user
        )

        nuevo_estado  = request.data.get('estado', '').strip()
        observaciones = request.data.get('observaciones', '').strip()

        # Fotos por categoría (solo para entregada/rechazada)
        foto_guia      = request.FILES.get('foto_guia')
        fotos_cliente  = request.FILES.getlist('fotos_cliente')

        # Validar estado
        if nuevo_estado not in ESTADOS_VALIDOS_TRANSPORTISTA:
            return Response(
                {'error': f'Estado "{nuevo_estado}" no es válido.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validar transición permitida
        from .serializers import NEXT_STATE_MAP
        if nuevo_estado not in NEXT_STATE_MAP.get(guide.estado, []):
            return Response(
                {'error': f'No se puede pasar de "{guide.estado}" a "{nuevo_estado}".'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validar fotos obligatorias por categoría
        if nuevo_estado in ESTADOS_REQUIEREN_FOTO:
            if not foto_guia:
                return Response(
                    {'error': 'La foto de la guía de despacho firmada es obligatoria.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not fotos_cliente:
                return Response(
                    {'error': 'Se requiere al menos una foto del cliente recepcionando los productos.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Crear etapa
        try:
            etapa = GuideStage.objects.create(
                guia=guide,
                estado=nuevo_estado,
                observaciones=observaciones or None,
            )
        except Exception as exc:
            logger.error('[UpdateEstado] Error creando GuideStage guia=%s: %s', pk, exc, exc_info=True)
            return Response({'error': 'Error interno al registrar la etapa.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Guardar foto de guía (solo una)
        foto_guia_obj = None
        if foto_guia:
            try:
                foto_guia_obj = GuideStagePhoto.objects.create(etapa=etapa, foto=foto_guia, orden=0, categoria='guia')
            except Exception as exc:
                logger.error('[UpdateEstado] Error guardando foto_guia guia=%s: %s', pk, exc, exc_info=True)
                etapa.delete()
                return Response({'error': 'Error al guardar la foto de la guía. Intenta nuevamente.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Guardar fotos del cliente (múltiples)
        for i, foto in enumerate(fotos_cliente):
            try:
                GuideStagePhoto.objects.create(etapa=etapa, foto=foto, orden=i, categoria='cliente')
            except Exception as exc:
                logger.error('[UpdateEstado] Error guardando foto_cliente[%d] guia=%s: %s', i, pk, exc, exc_info=True)
                etapa.delete()
                return Response({'error': 'Error al guardar una foto del cliente. Intenta nuevamente.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Actualizar guía
        try:
            guide.estado = nuevo_estado
            if nuevo_estado in ESTADOS_REQUIEREN_FOTO and not guide.fecha_envio:
                guide.fecha_envio = timezone.localdate()
            guide.save()
        except Exception as exc:
            logger.error('[UpdateEstado] Error guardando guide.save() guia=%s: %s', pk, exc, exc_info=True)
            etapa.delete()
            return Response({'error': 'Error interno al actualizar el estado.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Generar PDF backup de la foto de guía firmada (no fatal)
        if foto_guia_obj is not None and nuevo_estado in ESTADOS_REQUIEREN_FOTO:
            pdf_url = _upload_guide_pdf(foto_guia, guide)
            if pdf_url:
                foto_guia_obj.pdf_backup = pdf_url
                foto_guia_obj.save(update_fields=['pdf_backup'])

        # Notificaciones por correo (no fatales)
        send_seller_notification(guide)
        send_coordinator_notification(guide)

        try:
            serializer = DispatchGuideDetailSerializer(
                guide, context={'request': request}
            )
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as exc:
            logger.error('[UpdateEstado] Error serializando respuesta guia=%s: %s', pk, exc, exc_info=True)
            return Response({'estado': nuevo_estado, 'id': guide.id}, status=status.HTTP_200_OK)
