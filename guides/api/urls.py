from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import LoginView, MeView, MisGuiasView, GuiaDetailView, UpdateEstadoView

urlpatterns = [
    # Auth
    path('auth/login/',   LoginView.as_view(),        name='api_login'),
    path('auth/refresh/', TokenRefreshView.as_view(),  name='api_refresh'),
    path('auth/me/',      MeView.as_view(),             name='api_me'),

    # Guías
    path('mis-guias/',              MisGuiasView.as_view(),   name='api_mis_guias'),
    path('guias/<int:pk>/',         GuiaDetailView.as_view(), name='api_guia_detail'),
    path('guias/<int:pk>/estado/',  UpdateEstadoView.as_view(), name='api_update_estado'),
]
