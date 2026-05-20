from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group


class Command(BaseCommand):
    help = 'Crea los grupos de roles del sistema (Coordinador, Transportista)'

    def handle(self, *args, **options):
        for group_name in ['Coordinador', 'Transportista']:
            _, created = Group.objects.get_or_create(name=group_name)
            if created:
                self.stdout.write(self.style.SUCCESS(f'Grupo "{group_name}" creado'))
            else:
                self.stdout.write(f'Grupo "{group_name}" ya existe')
