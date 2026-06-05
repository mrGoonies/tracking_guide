from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from guides.models import DispatchGuide, GuideStage, GuideStagePhoto
from .permissions import IsTransportista
from .serializers import (
    CustomTokenObtainPairSerializer,
    DispatchGuideListSerializer,
    DispatchGuideDetailSerializer,
)

ESTADOS_REQUIEREN_FOTO = ('entregada', 'rechazada')
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
        fotos         = request.FILES.getlist('fotos')

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

        # Foto obligatoria al entregar o rechazar
        if nuevo_estado in ESTADOS_REQUIEREN_FOTO and not fotos:
            return Response(
                {'error': 'Se requiere al menos una foto al marcar como entregada o rechazada.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Crear etapa
        etapa = GuideStage.objects.create(
            guia=guide,
            estado=nuevo_estado,
            observaciones=observaciones or None,
        )

        # Guardar fotos
        for i, foto in enumerate(fotos):
            GuideStagePhoto.objects.create(etapa=etapa, foto=foto, orden=i)

        # Actualizar guía
        guide.estado = nuevo_estado
        if nuevo_estado in ESTADOS_REQUIEREN_FOTO and not guide.fecha_envio:
            guide.fecha_envio = timezone.localdate()
        guide.save()

        serializer = DispatchGuideDetailSerializer(
            guide, context={'request': request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)
