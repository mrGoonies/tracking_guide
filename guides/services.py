import logging

from django.conf import settings
from django.contrib.auth.models import User

logger = logging.getLogger(__name__)

_ESTADOS_NOTIFICACION = {'entregada', 'rechazada'}


# ── Helpers internos ──────────────────────────────────────────────────────────

def _get_mandrill_client():
    api_key = getattr(settings, 'MANDRILL_API_KEY', '')
    from_email = getattr(settings, 'MANDRILL_FROM_EMAIL', '')
    if not api_key or not from_email:
        return None
    try:
        import mailchimp_transactional
        return mailchimp_transactional.Client(api_key)
    except Exception as exc:
        logger.error('[Mandrill] Error creando cliente: %s', exc)
        return None


def _get_latest_stage(guide):
    """Devuelve la etapa más reciente con el estado actual de la guía."""
    return guide.etapas.filter(estado=guide.estado).order_by('-timestamp').first()


def _build_email_body(guide, stage):
    """HTML compartido entre notificaciones al vendedor y a coordinadores."""
    estado_label = 'Entregada' if guide.estado == 'entregada' else 'Rechazada'
    estado_color = '#2d7a35' if guide.estado == 'entregada' else '#c0392b'
    timestamp_str = stage.timestamp.strftime('%d/%m/%Y %H:%M') if stage else '—'

    map_html = (
        f'<p><a href="{guide.map_link}" style="color:#2d7a35;">Ver ubicación en Google Maps</a></p>'
        if guide.map_link
        else '<p>Sin link de mapa registrado.</p>'
    )

    foto_urls = []
    if stage:
        for foto_obj in stage.fotos.all():
            try:
                foto_urls.append(foto_obj.foto.url)
            except Exception:
                pass
        if stage.foto:
            try:
                foto_urls.append(stage.foto.url)
            except Exception:
                pass

    fotos_html = ''.join(
        f'<p style="margin:4px 0;"><a href="{url}" style="color:#2d7a35;">{url}</a></p>'
        for url in foto_urls
    ) or '<p>Sin fotografías adjuntas.</p>'

    return f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;">
      <div style="background:#2d7a35;padding:16px 24px;">
        <h2 style="color:#fff;margin:0;">Guía {guide.numero_guia} — {estado_label}</h2>
      </div>
      <div style="padding:24px;border:1px solid #e0e0e0;border-top:none;">
        <table style="border-collapse:collapse;width:100%;font-size:14px;">
          <tr><td style="padding:6px 0;color:#555;width:180px;"><strong>Cliente</strong></td>
              <td style="padding:6px 0;">{guide.cliente.nombre}</td></tr>
          <tr><td style="padding:6px 0;color:#555;"><strong>RUT</strong></td>
              <td style="padding:6px 0;">{guide.cliente.rut}</td></tr>
          <tr><td style="padding:6px 0;color:#555;"><strong>Nota de Venta</strong></td>
              <td style="padding:6px 0;">{guide.nv or '—'}</td></tr>
          <tr><td style="padding:6px 0;color:#555;"><strong>Vendedor / Asistente</strong></td>
              <td style="padding:6px 0;">{guide.get_vendedor_display()}</td></tr>
          <tr><td style="padding:6px 0;color:#555;"><strong>Fecha y hora</strong></td>
              <td style="padding:6px 0;">{timestamp_str}</td></tr>
          <tr><td style="padding:6px 0;color:#555;"><strong>Estado</strong></td>
              <td style="padding:6px 0;font-weight:700;color:{estado_color};">{estado_label}</td></tr>
        </table>

        <h3 style="margin-top:24px;font-size:14px;color:#333;border-bottom:1px solid #e0e0e0;padding-bottom:6px;">
          Ubicación del despacho
        </h3>
        {map_html}

        <h3 style="margin-top:24px;font-size:14px;color:#333;border-bottom:1px solid #e0e0e0;padding-bottom:6px;">
          Fotografías del transportista
        </h3>
        {fotos_html}
      </div>
    </div>
    """


def _send_message(client, *, to, subject, html_body, guide_numero):
    """Envía un mensaje Mandrill. Loguea el error y retorna False si falla."""
    from_email = getattr(settings, 'MANDRILL_FROM_EMAIL', '')
    try:
        client.messages.send({
            'message': {
                'html': html_body,
                'subject': subject,
                'from_email': from_email,
                'from_name': 'Irritec Logística',
                'to': to,
            }
        })
        return True
    except Exception as exc:
        logger.error(
            '[Mandrill] Error enviando correo. guia=%s destinatarios=%s error=%s',
            guide_numero, [r['email'] for r in to], exc, exc_info=True,
        )
        return False


# ── Funciones públicas ────────────────────────────────────────────────────────

def send_seller_notification(guide):
    """
    Notifica al vendedor/asistente (Seller.email) cuando la guía cambia a
    'entregada' o 'rechazada'. No lanza excepciones.
    """
    if guide.estado not in _ESTADOS_NOTIFICACION:
        return

    if not (guide.vendedor and guide.vendedor.email):
        logger.info(
            '[Notificación Vendedor] Sin email de vendedor configurado. guia=%s',
            guide.numero_guia,
        )
        return

    client = _get_mandrill_client()
    if not client:
        logger.warning(
            '[Notificación Vendedor] Mandrill no disponible (credenciales ausentes). guia=%s',
            guide.numero_guia,
        )
        return

    estado_label = 'entregados' if guide.estado == 'entregada' else 'rechazados'
    subject = (
        f'NV {guide.nv or guide.numero_guia} — '
        f'Productos {estado_label} para {guide.cliente.nombre}'
    )

    stage = _get_latest_stage(guide)
    sent = _send_message(
        client,
        to=[{'email': guide.vendedor.email, 'type': 'to'}],
        subject=subject,
        html_body=_build_email_body(guide, stage),
        guide_numero=guide.numero_guia,
    )
    if sent:
        logger.info(
            '[Notificación Vendedor] Enviado a %s. guia=%s',
            guide.vendedor.email, guide.numero_guia,
        )


def send_coordinator_notification(guide):
    """
    Notifica a todos los usuarios activos del grupo 'Coordinador' que tengan
    email cuando la guía cambia a 'entregada' o 'rechazada'. No lanza excepciones.
    """
    if guide.estado not in _ESTADOS_NOTIFICACION:
        return

    emails = list(
        User.objects.filter(groups__name='Coordinador', is_active=True)
        .exclude(email='')
        .values_list('email', flat=True)
    )
    if not emails:
        logger.info(
            '[Notificación Coordinadores] Sin coordinadores con email. guia=%s',
            guide.numero_guia,
        )
        return

    client = _get_mandrill_client()
    if not client:
        logger.warning(
            '[Notificación Coordinadores] Mandrill no disponible (credenciales ausentes). guia=%s',
            guide.numero_guia,
        )
        return

    estado_label = 'Entregada' if guide.estado == 'entregada' else 'Rechazada'
    subject = (
        f'[Logística] Guía {guide.numero_guia} — '
        f'{estado_label} para {guide.cliente.nombre}'
    )

    stage = _get_latest_stage(guide)
    sent = _send_message(
        client,
        to=[{'email': email, 'type': 'to'} for email in emails],
        subject=subject,
        html_body=_build_email_body(guide, stage),
        guide_numero=guide.numero_guia,
    )
    if sent:
        logger.info(
            '[Notificación Coordinadores] Enviado a %d coordinador(es). guia=%s',
            len(emails), guide.numero_guia,
        )
