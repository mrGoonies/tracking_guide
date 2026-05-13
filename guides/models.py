from django.db import models
from django.contrib.auth.models import User

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
    cliente = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='guias')
    usa_direccion_facturacion = models.BooleanField(default=True)
    direccion_entrega = models.TextField()
    map_link = models.URLField(blank=True, null=True)
    transportista = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='guias_asignadas')
    estado = models.CharField(max_length=20, choices=STATUS_CHOICES, default='emitida')
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    notas = models.TextField(blank=True, null=True)

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
    foto = models.ImageField(upload_to='guide_photos/%Y/%m/%d/', blank=True, null=True)
    observaciones = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Etapa de Guía"
        verbose_name_plural = "Etapas de Guías"
        ordering = ['-timestamp']

    def __str__(self):
        return f"Guía {self.guia.numero_guia} - {self.estado} ({self.timestamp})"
