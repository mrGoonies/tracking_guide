from django.contrib import admin
from .models import Client, DispatchGuide, GuideStage


class GuideStageInline(admin.TabularInline):
    """Inline para mostrar etapas dentro de la guía."""
    model = GuideStage
    extra = 0
    readonly_fields = ('timestamp',)
    fields = ('estado', 'timestamp', 'foto', 'observaciones')


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('rut', 'nombre', 'fecha_creacion')
    search_fields = ('rut', 'nombre')
    list_filter = ('fecha_creacion',)
    readonly_fields = ('fecha_creacion',)
    fieldsets = (
        ('Información Básica', {
            'fields': ('rut', 'nombre')
        }),
        ('Direcciones', {
            'fields': ('direccion_facturacion', 'direccion_entrega_preferida')
        }),
        ('Auditoría', {
            'fields': ('fecha_creacion',),
            'classes': ('collapse',)
        }),
    )


@admin.register(DispatchGuide)
class DispatchGuideAdmin(admin.ModelAdmin):
    list_display = ('numero_guia', 'cliente', 'estado', 'transportista', 'fecha_creacion')
    list_filter = ('estado', 'fecha_creacion')
    search_fields = ('numero_guia', 'cliente__nombre', 'cliente__rut')
    readonly_fields = ('fecha_creacion', 'fecha_actualizacion')
    inlines = [GuideStageInline]
    fieldsets = (
        ('Información de Guía', {
            'fields': ('numero_guia', 'cliente', 'estado')
        }),
        ('Dirección de Entrega', {
            'fields': ('usa_direccion_facturacion', 'direccion_entrega', 'map_link')
        }),
        ('Asignación', {
            'fields': ('transportista',)
        }),
        ('Observaciones', {
            'fields': ('notas',)
        }),
        ('Auditoría', {
            'fields': ('fecha_creacion', 'fecha_actualizacion'),
            'classes': ('collapse',)
        }),
    )


@admin.register(GuideStage)
class GuideStageAdmin(admin.ModelAdmin):
    list_display = ('guia', 'estado', 'timestamp')
    list_filter = ('estado', 'timestamp')
    search_fields = ('guia__numero_guia',)
    readonly_fields = ('timestamp',)
    fieldsets = (
        ('Etapa de Guía', {
            'fields': ('guia', 'estado', 'timestamp')
        }),
        ('Detalles', {
            'fields': ('foto', 'observaciones')
        }),
    )
