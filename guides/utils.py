import csv
from io import StringIO, TextIOWrapper
from django.db import transaction
from .models import Client


def is_admin(user):
    return user.is_staff


def is_coordinador(user):
    return user.groups.filter(name='Coordinador').exists()


def is_transportista(user):
    return user.groups.filter(name='Transportista').exists() and not user.is_staff


def get_home_url_for_user(user):
    """Retorna la URL de inicio según el rol del usuario."""
    if is_transportista(user):
        return 'transportista_guides'
    return 'guide_list'

def import_clients_from_csv(csv_file):
    """
    Importa clientes desde un archivo CSV.
    
    Formato esperado: Cuenta de cliente;Dirección;Nombre
    
    Returns:
        dict: {'success': int, 'errors': list, 'updated': int}
    """
    results = {
        'success': 0,
        'errors': [],
        'updated': 0,
        'total': 0
    }
    
    try:
        # Leer el archivo
        if isinstance(csv_file, str):
            content = csv_file
        else:
            content = csv_file.read()
            if isinstance(content, bytes):
                content = content.decode('utf-8')
        
        # Parsear el CSV con punto y coma como separador
        csv_reader = csv.DictReader(
            StringIO(content),
            fieldnames=['rut', 'direccion_facturacion', 'nombre'],
            delimiter=';'
        )
        
        # Saltar encabezado si existe
        next(csv_reader, None)
        
        with transaction.atomic():
            for row_num, row in enumerate(csv_reader, start=2):  # Comienza en 2 (después del header)
                try:
                    rut = row.get('rut', '').strip()
                    direccion = row.get('direccion_facturacion', '').strip()
                    nombre = row.get('nombre', '').strip()
                    
                    # Validar datos mínimos
                    if not rut or not nombre:
                        results['errors'].append(f"Fila {row_num}: RUT y nombre son obligatorios")
                        continue
                    
                    # Limpiar la dirección (remover saltos de línea múltiples)
                    direccion = ' '.join(direccion.split())
                    
                    results['total'] += 1
                    
                    # Crear o actualizar cliente
                    client, created = Client.objects.update_or_create(
                        rut=rut,
                        defaults={
                            'nombre': nombre,
                            'direccion_facturacion': direccion
                        }
                    )
                    
                    if created:
                        results['success'] += 1
                    else:
                        results['updated'] += 1
                        
                except Exception as e:
                    results['errors'].append(f"Fila {row_num}: {str(e)}")
        
    except csv.Error as e:
        results['errors'].append(f"Error al parsear CSV: {str(e)}")
    except Exception as e:
        results['errors'].append(f"Error general: {str(e)}")
    
    return results
