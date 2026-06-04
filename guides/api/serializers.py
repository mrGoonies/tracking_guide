from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from guides.models import Client, DispatchGuide, GuideStage, GuideStagePhoto


# ── Auth ────────────────────────────────────────────────────────────────────

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Agrega info del usuario al payload del login."""

    def validate(self, attrs):
        data = super().validate(attrs)
        data['username'] = self.user.username
        data['nombre'] = self.user.get_full_name() or self.user.username
        data['es_transportista'] = self.user.groups.filter(name='Transportista').exists()
        return data


# ── Fotos ────────────────────────────────────────────────────────────────────

class GuideStagePhotoSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = GuideStagePhoto
        fields = ['id', 'url', 'orden']

    def get_url(self, obj):
        request = self.context.get('request')
        if not obj.foto:
            return None
        try:
            url = obj.foto.url
            return request.build_absolute_uri(url) if request else url
        except Exception:
            return None


# ── Etapas ───────────────────────────────────────────────────────────────────

class GuideStageSerializer(serializers.ModelSerializer):
    fotos = GuideStagePhotoSerializer(many=True, read_only=True)
    foto_legacy = serializers.SerializerMethodField()

    class Meta:
        model = GuideStage
        fields = ['id', 'estado', 'timestamp', 'observaciones', 'fotos', 'foto_legacy']

    def get_foto_legacy(self, obj):
        """Foto antigua (campo foto directo) para registros previos al modelo GuideStagePhoto."""
        if not obj.foto:
            return None
        request = self.context.get('request')
        try:
            url = obj.foto.url
            return request.build_absolute_uri(url) if request else url
        except Exception:
            return None


# ── Cliente ──────────────────────────────────────────────────────────────────

class ClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Client
        fields = ['rut', 'nombre', 'direccion_facturacion', 'direccion_entrega_preferida']


# ── Guías ────────────────────────────────────────────────────────────────────

NEXT_STATE_MAP = {
    'emitida':   ['asignada', 'en_ruta', 'rechazada'],
    'asignada':  ['en_ruta', 'entregada', 'rechazada'],
    'en_ruta':   ['entregada', 'rechazada'],
    'entregada': ['cerrada'],
    'rechazada': ['cerrada'],
    'cerrada':   [],
}


class DispatchGuideListSerializer(serializers.ModelSerializer):
    """Serializer liviano para el listado de guías."""
    cliente_nombre = serializers.CharField(source='cliente.nombre', read_only=True)
    cliente_rut    = serializers.CharField(source='cliente.rut', read_only=True)
    estado_display = serializers.CharField(source='get_estado_display', read_only=True)

    class Meta:
        model = DispatchGuide
        fields = [
            'id', 'numero_guia', 'nv', 'estado', 'estado_display',
            'cliente_nombre', 'cliente_rut',
            'direccion_entrega', 'map_link',
            'fecha_despacho', 'fecha_creacion',
        ]


class DispatchGuideDetailSerializer(serializers.ModelSerializer):
    """Serializer completo para el detalle de una guía."""
    cliente         = ClientSerializer(read_only=True)
    etapas          = GuideStageSerializer(many=True, read_only=True)
    estado_display  = serializers.CharField(source='get_estado_display', read_only=True)
    vendedor_display = serializers.CharField(source='get_vendedor_display', read_only=True)
    proximos_estados = serializers.SerializerMethodField()

    class Meta:
        model = DispatchGuide
        fields = [
            'id', 'numero_guia', 'nv', 'nv_fecha_creacion',
            'estado', 'estado_display', 'proximos_estados',
            'cliente', 'direccion_entrega', 'map_link',
            'vendedor_display',
            'fecha_envio', 'fecha_despacho',
            'notas', 'fecha_creacion', 'fecha_actualizacion',
            'etapas',
        ]

    def get_proximos_estados(self, obj):
        """Devuelve los estados a los que puede transicionar esta guía."""
        return NEXT_STATE_MAP.get(obj.estado, [])
