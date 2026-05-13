# Tracking Guide - Prototipo MVP

Este proyecto es un prototipo de digitalización para mejorar la trazabilidad de guías de despacho en una empresa TI L1. El objetivo es reducir la dependencia del papel, centralizar la información y agregar evidencia fotográfica para resolver conflictos con clientes.

## Funcionalidades del MVP
- Importación de clientes desde CSV exportado del ERP.
- Creación de guías de despacho con autocompletado por RUT.
- Flujo de estados: Emitida → Asignada → En ruta → Entregada/Rechazada → Cerrada.
- Subida de fotos para evidencia (firma, rechazo).
- Dashboard básico para visibilidad gerencial.
- PWA para uso móvil-first.

## Tecnologías
- Django (backend full-stack)
- SQLite (base de datos)
- HTML/CSS/JS responsivo para móvil

## Instalación
1. Clonar el repo.
2. Crear entorno virtual: `python -m venv .venv`
3. Activar: `source .venv/bin/activate`
4. Instalar dependencias: `pip install -r requirements.txt`
5. Migrar: `python manage.py migrate`
6. Ejecutar: `python manage.py runserver`

## Etapas de desarrollo
- Etapa 1: Setup proyecto Django
- Etapa 2: Modelos y datos
- Etapa 3: Importación CSV clientes
- Etapa 4: Formulario nueva guía
- Etapa 5: Flujo estados y fotos
- Etapa 6: Roles y autenticación
- Etapa 7: PWA
- Etapa 8: Dashboard