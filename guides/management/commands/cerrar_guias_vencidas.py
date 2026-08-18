from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from guides.models import DispatchGuide, GuideStage

ESTADOS_CERRABLES = ('entregada', 'rechazada')


class Command(BaseCommand):
    help = (
        'Cierra automáticamente las guías en estado "entregada" o "rechazada" '
        'que llevan 24 horas o más desde su ingreso al sistema (fecha_creacion).'
    )

    def handle(self, *args, **options):
        limite = timezone.now() - timezone.timedelta(hours=24)

        guias = DispatchGuide.objects.filter(
            estado__in=ESTADOS_CERRABLES,
            fecha_creacion__lte=limite,
        )

        cerradas = 0
        for guia in guias.iterator():
            with transaction.atomic():
                GuideStage.objects.create(
                    guia=guia,
                    estado='cerrada',
                    observaciones='Cierre automático (24 horas desde el ingreso de la guía).',
                )
                guia.estado = 'cerrada'
                guia.save(update_fields=['estado', 'fecha_actualizacion'])
            cerradas += 1

        self.stdout.write(self.style.SUCCESS(f'{cerradas} guía(s) cerrada(s) automáticamente.'))
