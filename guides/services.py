import logging

from django.conf import settings

logger = logging.getLogger(__name__)

_ESTADOS_NOTIFICACION = {'entregada', 'rechazada'}


def send_guide_status_notification(guide, stage):
    """
    Envía correo transaccional vía Mandrill cuando una guía cambia a
    'entregada' o 'rechazada'.

    Destinatarios:
    - Logística (LOGISTICS_EMAIL, fijo en env)
    - Vendedor/asistente asociado a la guía (seller.email, si existe)

    No lanza excepción ante fallos: loguea el error y retorna sin interrumpir
    el flujo de cambio de estado.
    """
    if stage.estado not in _ESTADOS_NOTIFICACION:
        return

    api_key = getattr(settings, 'MANDRILL_API_KEY', '')
    from_email = getattr(settings, 'MANDRILL_FROM_EMAIL', '')
    logistics_email = getattr(settings, 'LOGISTICS_EMAIL', '')

    if not api_key or not from_email:
        logger.warning(
            '[Notificación] MANDRILL_API_KEY o MANDRILL_FROM_EMAIL no configurados. '
            'Correo omitido. guia=%s', guide.numero_guia
        )
        return

    # ── Destinatarios ─────────────────────────────────────────────────────
    to = []
    if logistics_email:
        to.append({'email': logistics_email, 'type': 'to'})

    if guide.vendedor and guide.vendedor.email:
        to.append({'email': guide.vendedor.email, 'type': 'cc'})

    if not to:
        logger.warning(
            '[Notificación] Sin destinatarios configurados. Correo omitido. guia=%s',
            guide.numero_guia
        )
        return

    # ── Datos del correo ──────────────────────────────────────────────────
    estado_label = 'Entregada' if stage.estado == 'entregada' else 'Rechazada'
    vendedor_nombre = guide.get_vendedor_display()
    timestamp_str = stage.timestamp.strftime('%d/%m/%Y %H:%M')

    map_html = (
        f'<p><a href="{guide.map_link}" style="color:#2d7a35;">Ver ubicación en Google Maps</a></p>'
        if guide.map_link
        else '<p>Sin link de mapa registrado.</p>'
    )

    foto_urls = []
    for foto_obj in stage.fotos.select_related().all():
        try:
            foto_urls.append(foto_obj.foto.url)
        except Exception:
            pass
    if stage.foto:
        try:
            foto_urls.append(stage.foto.url)
        except Exception:
            pass

    if foto_urls:
        fotos_html = ''.join(
            f'<p style="margin:4px 0;"><a href="{url}" style="color:#2d7a35;">{url}</a></p>'
            for url in foto_urls
        )
    else:
        fotos_html = '<p>Sin fotografías adjuntas.</p>'

    html_body = f"""
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
              <td style="padding:6px 0;">{vendedor_nombre}</td></tr>
          <tr><td style="padding:6px 0;color:#555;"><strong>Fecha y hora</strong></td>
              <td style="padding:6px 0;">{timestamp_str}</td></tr>
          <tr><td style="padding:6px 0;color:#555;"><strong>Estado</strong></td>
              <td style="padding:6px 0;font-weight:700;color:{'#2d7a35' if stage.estado == 'entregada' else '#c0392b'};">{estado_label}</td></tr>
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

    # ── Envío vía Mandrill ────────────────────────────────────────────────
    try:
        import mailchimp_transactional
        from mailchimp_transactional.api_client import ApiClientError

        client = mailchimp_transactional.Client(api_key)
        client.messages.send({
            'message': {
                'html': html_body,
                'subject': f'[{estado_label}] Guía {guide.numero_guia} — {guide.cliente.nombre}',
                'from_email': from_email,
                'from_name': 'Irritec Logística',
                'to': to,
            }
        })
        logger.info(
            '[Notificación] Correo enviado. guia=%s estado=%s destinatarios=%d',
            guide.numero_guia, stage.estado, len(to)
        )
    except Exception as exc:
        logger.error(
            '[Notificación] Error enviando correo. guia=%s estado=%s error=%s',
            guide.numero_guia, stage.estado, exc, exc_info=True
        )
