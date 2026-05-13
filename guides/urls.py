from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('clientes/importar/', views.import_clients, name='import_clients'),
    path('guias/', views.guide_list, name='guide_list'),
]