import io
import logging
import urllib.request
import zipfile
from collections import defaultdict
from datetime import datetime, time, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from guides.models import GuideStage
from guides.services import send_weekly_transportista_summary

logger = logging.getLogger(__name__)


def _sanitize(name):
    safe = ''.join(c if c.isalnum() or c in '-_ ' else '_' for c in str(name)).strip()
    return safe or 'sin_nombre'


def _fetch_bytes(url):
    with urllib.request.urlopen(url, timeout=15) as resp:
        return resp.read()


class Command(BaseCommand):
    help = (
        'Envía a LOGISTICS_EMAIL un ZIP con las guías que llegaron a estado '
        '"entregada" la semana pasada (lunes a domingo anterior), organizadas '
        'en una carpeta por transportista con el PDF firmado de cada guía. '
        'Pensado para la facturación semanal de los transportistas.'
    )

    def handle(self, *args, **options):
        hoy = timezone.localdate()
        inicio_semana_actual = hoy - timedelta(days=hoy.weekday())
        week_start = inicio_semana_actual - timedelta(days=7)
        week_end_exclusivo = inicio_semana_actual

        tz = timezone.get_current_timezone()
        start_dt = timezone.make_aware(datetime.combine(week_start, time.min), tz)
        end_dt = timezone.make_aware(datetime.combine(week_end_exclusivo, time.min), tz)

        etapas = (
            GuideStage.objects
            .filter(
                estado='entregada',
                timestamp__gte=start_dt,
                timestamp__lt=end_dt,
                guia__estado='entregada',
            )
            .select_related('guia', 'guia__transportista')
            .prefetch_related('fotos')
            .order_by('guia_id', '-timestamp')
        )

        vistos = set()
        por_transportista = defaultdict(list)
        for etapa in etapas:
            if etapa.guia_id in vistos:
                continue
            vistos.add(etapa.guia_id)
            transportista = etapa.guia.transportista
            if transportista:
                nombre = transportista.get_full_name() or transportista.username
            else:
                nombre = 'Sin transportista asignado'
            por_transportista[nombre].append(etapa)

        if not por_transportista:
            self.stdout.write(self.style.WARNING(
                'No hay guías entregadas la semana pasada. No se envía correo.'
            ))
            return

        buffer = io.BytesIO()
        resumen = []
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for nombre, etapas_transportista in por_transportista.items():
                carpeta = _sanitize(nombre)
                sin_pdf = []
                for etapa in etapas_transportista:
                    guia = etapa.guia
                    foto_guia = next(
                        (f for f in etapa.fotos.all() if f.categoria == 'guia'), None
                    )
                    pdf_bytes = None
                    if foto_guia and foto_guia.pdf_backup:
                        try:
                            pdf_bytes = _fetch_bytes(foto_guia.pdf_backup)
                        except Exception as exc:
                            logger.warning(
                                '[Resumen Semanal] No se pudo descargar PDF de guía %s: %s',
                                guia.numero_guia, exc,
                            )
                    if pdf_bytes:
                        zf.writestr(f'{carpeta}/{_sanitize(guia.numero_guia)}.pdf', pdf_bytes)
                    else:
                        sin_pdf.append(guia.numero_guia)
                resumen.append({
                    'transportista': nombre,
                    'cantidad': len(etapas_transportista),
                    'sin_pdf': sin_pdf,
                })

        zip_bytes = buffer.getvalue()
        enviado = send_weekly_transportista_summary(
            zip_bytes,
            week_start=week_start,
            week_end=week_end_exclusivo - timedelta(days=1),
            resumen=resumen,
        )

        total = sum(r['cantidad'] for r in resumen)
        if enviado:
            self.stdout.write(self.style.SUCCESS(
                f'Resumen semanal enviado. {total} guía(s) en {len(resumen)} transportista(s).'
            ))
        else:
            self.stdout.write(self.style.ERROR(
                'No se pudo enviar el resumen semanal (revisar logs).'
            ))
