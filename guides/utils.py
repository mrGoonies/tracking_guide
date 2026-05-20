def is_admin(user):
    return user.is_staff


def is_coordinador(user):
    return user.groups.filter(name='Coordinador').exists()


def is_transportista(user):
    return user.groups.filter(name='Transportista').exists() and not user.is_staff


def get_home_url_for_user(user):
    if is_transportista(user):
        return 'transportista_guides'
    return 'hub'
