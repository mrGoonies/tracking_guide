"""Validación compartida de evidencia fotográfica para web y API."""

from PIL import Image, UnidentifiedImageError


MAX_PHOTO_MB = 25
MAX_PHOTO_SIZE = MAX_PHOTO_MB * 1024 * 1024
MAX_EVIDENCE_PHOTOS = 5
ALLOWED_IMAGE_FORMATS = {'JPEG', 'PNG', 'WEBP'}


def evidence_label(state):
    if state == 'rechazada':
        return 'evidencia del rechazo'
    return 'evidencia de la entrega'


def _validate_image(uploaded_file, label):
    errors = []
    if uploaded_file.size > MAX_PHOTO_SIZE:
        errors.append(f'{label} supera el máximo de {MAX_PHOTO_MB} MB.')

    try:
        uploaded_file.seek(0)
        image = Image.open(uploaded_file)
        image.verify()
        # El MIME informado por el dispositivo puede no coincidir con el
        # contenido (p. ej. image/jpg o application/octet-stream).
        if image.format not in ALLOWED_IMAGE_FORMATS:
            errors.append(f'{label} debe ser una imagen JPG, PNG o WEBP.')
    except (UnidentifiedImageError, OSError, SyntaxError):
        errors.append(f'{label} no contiene una imagen válida.')
    finally:
        uploaded_file.seek(0)

    return errors


def validate_required_evidence(state, guide_photos, evidence_photos):
    """
    Valida presencia, cantidad, tamaño y contenido real.

    Retorna errores separados para que cada interfaz indique exactamente qué
    categoría debe corregirse.
    """
    guide_photos = list(guide_photos or [])
    evidence_photos = list(evidence_photos or [])
    errors = {'foto_guia': [], 'fotos_evidencia': []}

    if len(guide_photos) == 0:
        errors['foto_guia'].append(
            'Falta la foto de la guía de despacho firmada.'
        )
    elif len(guide_photos) > 1:
        errors['foto_guia'].append(
            'Debes adjuntar exactamente una foto de la guía de despacho firmada.'
        )

    label = evidence_label(state)
    if len(evidence_photos) == 0:
        errors['fotos_evidencia'].append(
            f'Falta al menos una foto como {label}.'
        )
    elif len(evidence_photos) > MAX_EVIDENCE_PHOTOS:
        errors['fotos_evidencia'].append(
            f'Puedes adjuntar como máximo {MAX_EVIDENCE_PHOTOS} fotos de {label}.'
        )

    for photo in guide_photos:
        errors['foto_guia'].extend(
            _validate_image(photo, 'La foto de la guía')
        )
    for index, photo in enumerate(evidence_photos, start=1):
        errors['fotos_evidencia'].extend(
            _validate_image(photo, f'La foto de evidencia {index}')
        )

    return {field: messages for field, messages in errors.items() if messages}
