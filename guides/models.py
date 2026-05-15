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
    cliente = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='guias')
    usa_direccion_facturacion = models.BooleanField(default=True)
    direccion_entrega = models.TextField()
    map_link = models.URLField(blank=True, null=True)
    transportista = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='guias_asignadas')
    vendedor = models.ForeignKey(Seller, on_delete=models.SET_NULL, null=True, blank=True, related_name='guias_emitidas')
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
    foto = models.ImageField(upload_to='guide_photos/%Y/%m/%d/', blank=True, null=True)
    observaciones = models.TextField(blank=True, null=True)

    class Meta:
        verbose_name = "Etapa de Guía"
        verbose_name_plural = "Etapas de Guías"
        ordering = ['-timestamp']

    def __str__(self):
        return f"Guía {self.guia.numero_guia} - {self.estado} ({self.timestamp})"
