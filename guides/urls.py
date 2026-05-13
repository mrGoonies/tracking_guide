from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('clientes/importar/', views.import_clients, name='import_clients'),
    path('clientes/buscar/', views.search_client_by_rut, name='search_client'),
    path('guias/', views.guide_list, name='guide_list'),
    path('guias/nueva/', views.create_guide, name='create_guide'),
]