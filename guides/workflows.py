"""Reglas compartidas del flujo de estados de las guías."""

from .utils import is_coordinador, is_transportista


STATE_TRANSITIONS = {
    'emitida': ('asignada', 'en_ruta', 'rechazada'),
    'asignada': ('en_ruta', 'entregada', 'rechazada'),
    'en_ruta': ('entregada', 'rechazada'),
    'entregada': ('cerrada',),
    'rechazada': ('cerrada',),
    'cerrada': (),
}


def allowed_state_values(guide, user):
    """Estados destino que el usuario puede aplicar a la guía."""
    if not user or not user.is_authenticated:
        return ()

    if is_transportista(user):
        if guide.transportista_id != user.id:
            return ()
        return tuple(
            state for state in STATE_TRANSITIONS.get(guide.estado, ())
            if state != 'cerrada'
        )

    if user.is_staff or is_coordinador(user):
        return STATE_TRANSITIONS.get(guide.estado, ())

    return ()


def allowed_state_choices(guide, user):
    """Opciones con etiquetas del modelo, limitadas por estado, rol y propiedad."""
    labels = dict(guide.STATUS_CHOICES)
    return [(state, labels[state]) for state in allowed_state_values(guide, user)]


def validate_state_transition(guide, requested_state, user):
    """Retorna ``(es_valida, mensaje)`` sin producir efectos secundarios."""
    if is_transportista(user) and guide.transportista_id != user.id:
        return False, 'No tienes acceso a esta guía.'

    if requested_state == 'cerrada' and is_transportista(user):
        return False, 'Los transportistas no pueden cerrar guías.'

    if requested_state not in allowed_state_values(guide, user):
        return (
            False,
            f'No se puede pasar de "{guide.get_estado_display()}" '
            f'a "{dict(guide.STATUS_CHOICES).get(requested_state, requested_state)}".',
        )

    return True, ''
