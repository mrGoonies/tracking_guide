from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def admin_or_coordinador_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if request.user.is_staff or request.user.groups.filter(name='Coordinador').exists():
            return view_func(request, *args, **kwargs)
        messages.error(request, 'No tienes permisos para acceder a esta sección.')
        return redirect('transportista_guides')
    return wrapper


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if request.user.is_staff:
            return view_func(request, *args, **kwargs)
        messages.error(request, 'Solo administradores pueden acceder a esta sección.')
        return redirect('transportista_guides')
    return wrapper
