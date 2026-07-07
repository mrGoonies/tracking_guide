import os
import uuid

from django.db import models
from django.contrib.auth.models import User


def _guide_photo_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower() or '.jpg'
    from django.utils import timezone
    now = timezone.now()
    try:
        # GuideStage tiene FK directa; GuideStagePhoto llega via etapa
        if hasattr(instance, 'guia'):
            numero_guia = instance.guia.numero_guia
        else:
            numero_guia = instance.etapa.guia.numero_guia
        safe_guia = ''.join(c if c.isalnum() or c in '-_' else '_' for c in str(numero_guia))
    except Exception:
        safe_guia = 'sin_guia'
    return f"tracking/guide_photos/{now.year}/{now.month:02d}/{now.day:02d}/{safe_guia}/{uuid.uuid4().hex[:16]}{ext}"


def _guide_pdf_path(instance, filename):
    short_name = f"{uuid.uuid4().hex[:16]}.pdf"
    from django.utils import timezone
    now = timezone.now()
    return f"tracking/guide_pdfs/{now.year}/{now.month:02d}/{now.day:02d}/{short_name}"


def _pdf_storage():
    """Storage para PDFs: filesystem en dev, Cloudinary raw en prod."""
    from django.conf import settings
    if settings.DEBUG:
        from django.core.files.storage import FileSystemStorage
        return FileSystemStorage()
    from cloudinary_storage.storage import RawMediaCloudinaryStorage
    return RawMediaCloudinaryStorage()

class Client(models.Model):
    """Modelo para almacenar información de clientes."""
    rut = models.CharField(max_length=20, unique=True)
    nombre = models.CharField(max_length=200)
    direccion_facturacion = models.TextField()
    direccion_entrega_preferida = models.TextField(blank=True, null=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"
        ordering = ['-fecha_creacion']

    def __str__(self):
        return f"{self.rut} - {self.nombre}"


class Seller(models.Model):
    """Modelo para vendedores y asistentes comerciales."""
    nombre = models.CharField(max_length=255, unique=True)
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Vendedor / Asistente"
        verbose_name_plural = "Vendedores / Asistentes"
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class DispatchGuide(models.Model):
    """Modelo para guías de despacho."""
    STATUS_CHOICES = [
        ('emitida', 'Emitida'),
        ('asignada', 'Asignada'),
        ('en_ruta', 'En Ruta'),
        ('entregada', 'Entregada'),
        ('rechazada', 'Rechazada'),
        ('cerrada', 'Cerrada'),
    ]

    numero_guia = models.CharField(max_length=100, unique=True)
    nv = models.CharField(max_length=100, blank=True, null=True, verbose_name='Nota de Venta')
    nv_fecha_creacion = models.DateField(blank=True, null=True, verbose_name='Fecha creación NV')
    cliente = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='guias')
    usa_direccion_facturacion = models.BooleanField(default=True)
    direccion_entrega = models.TextField()
    map_link = models.URLField(blank=True, null=True)
    transportista = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='guias_asignadas')
    vendedor = models.ForeignKey(Seller, on_delete=models.SET_NULL, null=True, blank=True, related_name='guias_emitidas')
    fecha_envio = models.DateField(blank=True, null=True)
    fecha_despacho = models.DateField(blank=True, null=True)
    vendedor_nombre = models.CharField(max_length=255, blank=True, null=True)
    estado = models.CharField(max_length=20, choices=STATUS_CHOICES, default='emitida')
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    notas = models.TextField(blank=True, null=True)

    def get_vendedor_display(self):
        if self.vendedor_nombre:
            return self.vendedor_nombre
        if self.vendedor:
            return self.vendedor.nombre
        return 'Sin vendedor asignado'

    class Meta:
        verbose_name = "Guía de Despacho"
        verbose_name_plural = "Guías de Despacho"
        ordering = ['-fecha_creacion']

    def __str__(self):
        return f"Guía {self.numero_guia} - {self.cliente.nombre}"


class GuideStage(models.Model):
    """Modelo para el historial de etapas de una guía."""
    STATUS_CHOICES = [
        ('emitida', 'Emitida'),
        ('asignada', 'Asignada'),
        ('en_ruta', 'En Ruta'),
        ('entregada', 'Entregada'),
        ('rechazada', 'Rechazada'),
        ('cerrada', 'Cerrada'),
    ]

    guia = models.ForeignKey(DispatchGuide, on_delete=models.CASCADE, related_name='etapas')
    estado = models.CharField(max_length=20, choices=STATUS_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)
    foto = models.ImageField(upload_to=_guide_photo_path, max_length=500, blank=True, null=True)
    observaciones = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Etapa de Guía"
        verbose_name_plural = "Etapas de Guías"
        ordering = ['-timestamp']

    def __str__(self):
        return f"Guía {self.guia.numero_guia} - {self.estado} ({self.timestamp})"


class GuideStagePhoto(models.Model):
    """Fotos de una etapa, clasificadas por categoría."""
    CATEGORIA_CHOICES = [
        ('guia',    'Guía de Despacho'),
        ('cliente', 'Cliente'),
        ('general', 'General'),
    ]

    etapa      = models.ForeignKey(GuideStage, on_delete=models.CASCADE, related_name='fotos')
    foto       = models.ImageField(upload_to=_guide_photo_path, max_length=500)
    orden      = models.PositiveSmallIntegerField(default=0)
    categoria  = models.CharField(max_length=20, choices=CATEGORIA_CHOICES, default='general')
    pdf_backup = models.FileField(
        upload_to=_guide_pdf_path,
        storage=_pdf_storage,
        max_length=500,
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Foto de Etapa"
        verbose_name_plural = "Fotos de Etapas"
        ordering = ['categoria', 'orden', 'id']

    def __str__(self):
        return f"{self.get_categoria_display()} — Foto {self.orden + 1} — {self.etapa}"


class DeletedGuideNumber(models.Model):
    """
    Registro de números de guía eliminados manualmente.
    Evita que el import Excel re-cree guías que fueron borradas a propósito.
    Para permitir la re-importación, borrar el registro desde el admin.
    """
    numero_guia       = models.CharField(max_length=100, unique=True)
    fecha_eliminacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Número de guía eliminada"
        verbose_name_plural = "Números de guías eliminadas"
        ordering = ['-fecha_eliminacion']

    def __str__(self):
        return f"#{self.numero_guia} (eliminada {self.fecha_eliminacion:%d/%m/%Y})"
