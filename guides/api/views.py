import logging

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

logger = logging.getLogger(__name__)

from guides.models import DispatchGuide, GuideStage, GuideStagePhoto
from guides.services import (
    send_seller_notification,
    send_coordinator_notification,
    generate_guide_pdf_backup,
)
from guides.workflows import validate_state_transition
from guides.photo_validation import validate_required_evidence
from .permissions import IsTransportista
from .serializers import (
    CustomTokenObtainPairSerializer,
    DispatchGuideListSerializer,
    DispatchGuideDetailSerializer,
)

ESTADOS_REQUIEREN_FOTO = DispatchGuide.ESTADOS_REQUIEREN_FOTO

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
        fotos_guia = request.FILES.getlist('foto_guia')
        # ``fotos_cliente`` se conserva como alias para clientes móviles existentes.
        fotos_evidencia = (
            request.FILES.getlist('fotos_evidencia')
            or request.FILES.getlist('fotos_cliente')
        )

        transition_is_valid, transition_error = validate_state_transition(
            guide, nuevo_estado, request.user
        )
        if not transition_is_valid:
            return Response(
                {'error': transition_error},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validar fotos obligatorias por categoría
        if nuevo_estado in ESTADOS_REQUIEREN_FOTO:
            evidence_errors = validate_required_evidence(
                nuevo_estado, fotos_guia, fotos_evidencia
            )
            if evidence_errors:
                return Response(
                    {'error': 'La evidencia fotográfica es inválida.', 'campos': evidence_errors},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            foto_guia = fotos_guia[0]
        else:
            foto_guia = fotos_guia[0] if fotos_guia else None

        # Guardar etapa, fotos y estado como una sola operación.
        try:
            with transaction.atomic():
                guide = DispatchGuide.objects.select_for_update().get(
                    id=pk, transportista=request.user
                )
                transition_is_valid, transition_error = validate_state_transition(
                    guide, nuevo_estado, request.user
                )
                if not transition_is_valid:
                    transaction.set_rollback(True)
                    return Response(
                        {'error': transition_error},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                etapa = GuideStage.objects.create(
                    guia=guide,
                    estado=nuevo_estado,
                    observaciones=observaciones or None,
                )

                foto_guia_obj = None
                if foto_guia:
                    foto_guia_obj = GuideStagePhoto.objects.create(
                        etapa=etapa,
                        foto=foto_guia,
                        orden=0,
                        categoria='guia',
                    )

                for i, foto in enumerate(fotos_evidencia):
                    GuideStagePhoto.objects.create(
                        etapa=etapa,
                        foto=foto,
                        orden=i,
                        categoria='cliente',
                    )

                guide.estado = nuevo_estado
                if nuevo_estado in ESTADOS_REQUIEREN_FOTO and not guide.fecha_envio:
                    guide.fecha_envio = timezone.localdate()
                guide.save()
        except Exception as exc:
            logger.error(
                '[UpdateEstado] Error guardando cambio completo guia=%s: %s',
                pk, exc, exc_info=True
            )
            return Response(
                {'error': 'No fue posible guardar el cambio ni sus fotos. Intenta nuevamente.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Generar PDF de la guía firmada (no fatal). pdf_bytes se usa para
        # adjuntarlo al correo; el backup en Cloudinary es best-effort.
        pdf_bytes = None
        if foto_guia_obj is not None and nuevo_estado in ESTADOS_REQUIEREN_FOTO:
            pdf_bytes, pdf_url = generate_guide_pdf_backup(foto_guia, guide)
            if pdf_url:
                foto_guia_obj.pdf_backup = pdf_url
                foto_guia_obj.save(update_fields=['pdf_backup'])

        # Notificaciones por correo (no fatales)
        send_seller_notification(guide, pdf_bytes=pdf_bytes)
        send_coordinator_notification(guide, pdf_bytes=pdf_bytes)

        try:
            serializer = DispatchGuideDetailSerializer(
                guide, context={'request': request}
            )
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as exc:
            logger.error('[UpdateEstado] Error serializando respuesta guia=%s: %s', pk, exc, exc_info=True)
            return Response({'estado': nuevo_estado, 'id': guide.id}, status=status.HTTP_200_OK)
