import base64
import io
import logging

from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone

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


def _generate_pdf_bytes(image_file):
    """Convierte una foto (guía de despacho firmada) a PDF en memoria."""
    from PIL import Image
    image_file.seek(0)
    img = Image.open(image_file)
    if img.mode not in ('RGB', 'L'):
        img = img.convert('RGB')
    buf = io.BytesIO()
    img.save(buf, format='PDF')
    return buf.getvalue()


def generate_guide_pdf_backup(image_file, guide):
    """
    Convierte la foto de la guía firmada a PDF y la sube a Cloudinary como
    respaldo (solo en producción, igual que las fotos).

    Devuelve (pdf_bytes, secure_url). pdf_bytes se retorna siempre que la
    conversión funcione (se usa para adjuntarlo al correo); secure_url es
    None en DEBUG o si la subida a Cloudinary falla — ninguno de los dos
    casos es fatal para el flujo que llama a esta función.
    """
    try:
        pdf_bytes = _generate_pdf_bytes(image_file)
    except Exception as exc:
        logger.error('[PDF] Error generando PDF. guia=%s: %s', guide.numero_guia, exc, exc_info=True)
        return None, None

    if settings.DEBUG:
        return pdf_bytes, None

    import cloudinary.uploader

    now = timezone.now()
    safe_guia = ''.join(c if c.isalnum() or c in '-_' else '_' for c in str(guide.numero_guia))
    public_id = (
        f"tracking/guide_pdfs/{now.year}/{now.month:02d}/{now.day:02d}/"
        f"GUIA_DESPACHO_{safe_guia}.pdf"
    )
    try:
        result = cloudinary.uploader.upload(
            io.BytesIO(pdf_bytes),
            resource_type='raw',
            public_id=public_id,
            overwrite=True,
        )
        return pdf_bytes, result.get('secure_url')
    except Exception as exc:
        logger.error('[PDF] Error subiendo PDF a Cloudinary. guia=%s: %s', guide.numero_guia, exc, exc_info=True)
        return pdf_bytes, None


def _build_email_body(guide, stage, has_pdf_attachment=False):
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

    pdf_html = (
        '<p style="margin-top:16px;padding:10px 14px;background:#e8f5e9;'
        'border-radius:6px;color:#1b5e20;font-weight:600;">'
        '📎 Se adjunta la guía de despacho firmada en PDF.</p>'
        if has_pdf_attachment else ''
    )

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
        {pdf_html}
      </div>
    </div>
    """


def _build_pdf_attachment(pdf_bytes, guide):
    return {
        'type': 'application/pdf',
        'name': f'NotaVenta_Firmada_{guide.numero_guia}.pdf',
        'content': base64.b64encode(pdf_bytes).decode('ascii'),
    }


_ESTADOS_ENTREGA_OK = {'sent', 'queued', 'scheduled'}


def _send_message(client, *, to, subject, html_body, guide_numero, attachments=None):
    """
    Envía un mensaje Mandrill. Mandrill no lanza excepción cuando rechaza a un
    destinatario puntual (dirección inválida, bloqueada en su rejection
    blacklist por bounces previos, etc.) — lo informa en el status de cada
    destinatario dentro de la respuesta. Por eso, además de capturar errores
    de la llamada, se revisa esa respuesta y se loguea cada destinatario que
    no haya quedado 'sent'/'queued'/'scheduled'.

    Retorna True si al menos un destinatario recibió el correo.
    """
    from_email = getattr(settings, 'MANDRILL_FROM_EMAIL', '')
    message = {
        'html': html_body,
        'subject': subject,
        'from_email': from_email,
        'from_name': 'Irritec Logística',
        'to': to,
    }
    if attachments:
        message['attachments'] = attachments
    try:
        response = client.messages.send({'message': message})
    except Exception as exc:
        logger.error(
            '[Mandrill] Error enviando correo. guia=%s destinatarios=%s error=%s',
            guide_numero, [r['email'] for r in to], exc, exc_info=True,
        )
        return False

    sent_ok = False
    for result in response:
        if result.get('status') in _ESTADOS_ENTREGA_OK:
            sent_ok = True
        else:
            logger.warning(
                '[Mandrill] Destinatario no recibió el correo. guia=%s email=%s '
                'status=%s motivo=%s',
                guide_numero, result.get('email'), result.get('status'),
                result.get('reject_reason'),
            )
    return sent_ok


# ── Funciones públicas ────────────────────────────────────────────────────────

def send_seller_notification(guide, pdf_bytes=None):
    """
    Notifica al vendedor/asistente (Seller.email) cuando la guía cambia a
    'entregada' o 'rechazada'. Si se entrega `pdf_bytes` (la guía firmada
    convertida a PDF), se adjunta al correo. No lanza excepciones.
    """
    if guide.estado not in _ESTADOS_NOTIFICACION:
        return

    if not (guide.vendedor and guide.vendedor.email):
        logger.warning(
            '[Notificación Vendedor] Sin email de vendedor configurado (vendedor=%s, vendedor_nombre=%s). guia=%s',
            guide.vendedor_id, guide.vendedor_nombre, guide.numero_guia,
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
    attachments = [_build_pdf_attachment(pdf_bytes, guide)] if pdf_bytes else None
    sent = _send_message(
        client,
        to=[{'email': guide.vendedor.email, 'type': 'to'}],
        subject=subject,
        html_body=_build_email_body(guide, stage, has_pdf_attachment=bool(pdf_bytes)),
        guide_numero=guide.numero_guia,
        attachments=attachments,
    )
    if sent:
        logger.info(
            '[Notificación Vendedor] Enviado a %s. guia=%s',
            guide.vendedor.email, guide.numero_guia,
        )


def send_coordinator_notification(guide, pdf_bytes=None):
    """
    Notifica a todos los usuarios activos del grupo 'Coordinador' que tengan
    email cuando la guía cambia a 'entregada' o 'rechazada'. Si se entrega
    `pdf_bytes` (la guía firmada convertida a PDF), se adjunta al correo.
    No lanza excepciones.
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
    attachments = [_build_pdf_attachment(pdf_bytes, guide)] if pdf_bytes else None
    sent = _send_message(
        client,
        to=[{'email': email, 'type': 'to'} for email in emails],
        subject=subject,
        html_body=_build_email_body(guide, stage, has_pdf_attachment=bool(pdf_bytes)),
        guide_numero=guide.numero_guia,
        attachments=attachments,
    )
    if sent:
        logger.info(
            '[Notificación Coordinadores] Enviado a %d coordinador(es). guia=%s',
            len(emails), guide.numero_guia,
        )
