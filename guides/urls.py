from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),
    path('clientes/buscar/', views.search_client_by_rut, name='search_client'),
    path('guias/', views.guide_list, name='guide_list'),
    path('guias/nueva/', views.create_guide, name='create_guide'),
    path('guias/<int:guide_id>/', views.guide_detail, name='guide_detail'),
    path('guias/exportar-planificacion/', views.export_route_planning, name='export_route_planning'),
    path('transportista/mis-guias/', views.transportista_guides, name='transportista_guides'),
    path('inicio/', views.hub, name='hub'),
    path('reportes/transportistas/', views.transportista_report, name='transportista_report'),
    path('clientes/importar/', views.import_clients, name='import_clients'),
]