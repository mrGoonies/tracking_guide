from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import User
from .models import Client, DispatchGuide, GuideStage, Seller


class GuideStageInline(admin.TabularInline):
    """Inline para mostrar etapas dentro de la guía."""
    model = GuideStage
    extra = 0
    readonly_fields = ('timestamp',)
    fields = ('estado', 'timestamp', 'foto', 'observaciones')


@admin.register(Seller)
class SellerAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'activo', 'fecha_creacion')
    list_filter = ('activo', 'fecha_creacion')
    search_fields = ('nombre',)
    readonly_fields = ('fecha_creacion',)
    fieldsets = (
        ('Información', {
            'fields': ('nombre', 'activo')
        }),
        ('Auditoría', {
            'fields': ('fecha_creacion',),
            'classes': ('collapse',)
        }),
    )


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
    list_display = ('numero_guia', 'cliente', 'estado', 'transportista', 'get_vendedor_display', 'fecha_creacion')
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
            'fields': ('transportista', 'vendedor', 'vendedor_nombre')
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


admin.site.unregister(User)

@admin.register(User)
class CustomUserAdmin(DjangoUserAdmin):
    list_display = ('username', 'email', 'get_full_name', 'is_active', 'is_staff')
    list_filter = ('is_active', 'is_staff', 'groups', 'date_joined')
    search_fields = ('username', 'first_name', 'last_name', 'email')
    ordering = ('-date_joined',)
    
    fieldsets = (
        ('Credenciales', {
            'fields': ('username', 'password')
        }),
        ('Información Personal', {
            'fields': ('first_name', 'last_name', 'email')
        }),
        ('Permisos', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
            'classes': ('collapse',)
        }),
        ('Información de Sesión', {
            'fields': ('last_login', 'date_joined'),
            'classes': ('collapse',)
        }),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2'),
        }),
        ('Información Personal', {
            'classes': ('wide',),
            'fields': ('first_name', 'last_name', 'email'),
        }),
        ('Permisos', {
            'classes': ('wide',),
            'fields': ('is_active', 'is_staff', 'groups'),
        }),
    )
