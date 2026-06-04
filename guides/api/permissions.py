from rest_framework.permissions import BasePermission


class IsTransportista(BasePermission):
    """Solo usuarios del grupo Transportista pueden acceder."""
    message = 'Acceso restringido a transportistas.'

    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.groups.filter(name='Transportista').exists()
        )
