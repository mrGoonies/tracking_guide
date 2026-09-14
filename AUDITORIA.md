# Auditoría técnica — Tracking Guide

Fecha: 2026-08-20
Alcance: revisión de código real (`guides/`, `tracking_guide/`, `render.yaml`, `requirements.txt`, `pyproject.toml`, `uv.lock`) contra lo descrito en `CLAUDE.md`. No se modificó ningún archivo de código.

## Tabla resumen

| # | Hallazgo | Severidad | Archivo:línea | Estado |
|---|----------|-----------|----------------|--------|
| 1 | Las 3 fuentes de lógica de estado están sincronizadas hoy | Media (riesgo estructural, no bug actual) | `guides/views.py:361-368`, `guides/api/serializers.py:71-78`, `guides/api/views.py:28` | Confirmado (sin divergencia actual) |
| 1b | `ESTADOS_VALIDOS_TRANSPORTISTA` es redundante con `NEXT_STATE_MAP` y puede divergir en silencio | Media | `guides/api/views.py:28,103,111` | Confirmado |
| 2 | `guides/tests.py` está vacío, 0% cobertura | Alta | `guides/tests.py:1-3` | Confirmado |
| 3 | Notificaciones/PDF/Cloudinary fallan en silencio, sin alerta externa | Alta | `guides/services.py:56-83, 216-313` | Confirmado |
| 4 | Storage depende 100% de `DEBUG`; sin guardas si `DEBUG=True` en prod | Alta | `tracking_guide/settings.py:128-139` | Confirmado |
| 5 | `requirements.txt` y `pyproject.toml`/`uv.lock` divergen en versiones y en el propio framework de dependencias | Media | `requirements.txt:2,21`, `pyproject.toml:7-11`, `uv.lock` | Confirmado |
| 6 | Limpieza de `vendedor_nombre` es asimétrica entre alta manual e importación Excel | Media | `guides/views.py:298-299` vs `guides/views.py:817-826` | Confirmado |
| 7 | Ningún endpoint `/api/` usa `SessionAuthentication`; todos dependen de JWT | — | `guides/api/*.py`, `tracking_guide/settings.py:187-197` | Descartado (no hay riesgo) |
| 8 | Cron `cerrar_guias_vencidas` no tiene logging estructurado de éxito/fallo ni monitoreo de heartbeat | Media | `guides/management/commands/cerrar_guias_vencidas.py:36`, `render.yaml:23-37` | Confirmado |
| 9 | `GuideStage.foto` (legado) sigue activo en templates, admin y API, no es código muerto | Baja (doc desactualizada) | `guides/templates/guides/guide_detail.html:561-563`, `guides/api/serializers.py:49-58` | Documentación desactualizada (CLAUDE.md lo trata como reemplazado del todo) |
| 10 | `transportista_report` calcula promedios en Python, con `list(guide.etapas.all())` por guía (evita N+1 por el prefetch, pero repite trabajo en Python) | Baja/Media (depende de volumen) | `guides/views.py:441-497` | Confirmado, impacto bajo hoy |
| 11 (extra) | `GuideStagePhoto` no está registrado en el admin de Django | Baja | `guides/admin.py:1-4` | Hallazgo adicional |
| 12 (extra) | No existe ningún servicio de monitoreo/alerting (Sentry, etc.) en el proyecto | Alta | (ausencia, ver requirements.txt) | Hallazgo adicional |
| 13 (extra) | `pyproject.toml` describe una dependencia inexistente (`django-rest-framework`, con guion, no es el paquete PyPI real) | Baja | `pyproject.toml:8` | Confirmado |

---

## 1. Lógica de estado duplicada

Comparación línea a línea de las tres fuentes:

**`guides/views.py:361-368`** (`next_state_map` dentro de `guide_detail`):
```python
next_state_map = {
    'emitida': [('asignada', 'Asignar'), ('en_ruta', 'En Ruta'), ('rechazada', 'Rechazada')],
    'asignada': [('en_ruta', 'En Ruta'), ('entregada', 'Entregada'), ('rechazada', 'Rechazada')],
    'en_ruta': [('entregada', 'Entregada'), ('rechazada', 'Rechazada')],
    'entregada': [('cerrada', 'Cerrar')],
    'rechazada': [('cerrada', 'Cerrar')],
    'cerrada': [],
}
```

**`guides/api/serializers.py:71-78`** (`NEXT_STATE_MAP`):
```python
NEXT_STATE_MAP = {
    'emitida':   ['asignada', 'en_ruta', 'rechazada'],
    'asignada':  ['en_ruta', 'entregada', 'rechazada'],
    'en_ruta':   ['entregada', 'rechazada'],
    'entregada': ['cerrada'],
    'rechazada': ['cerrada'],
    'cerrada':   [],
}
```

Los conjuntos de claves/valores son idénticos (solo cambia la forma: tuplas con label vs. lista plana). **Hoy están sincronizados**, sin transiciones permitidas en un lugar y prohibidas en otro.

**`guides/api/views.py:28`**:
```python
ESTADOS_VALIDOS_TRANSPORTISTA = {'asignada', 'en_ruta', 'entregada', 'rechazada'}
```
Este set se usa en `guides/api/views.py:103` como primer filtro (`if nuevo_estado not in ESTADOS_VALIDOS_TRANSPORTISTA`) antes de validar la transición real contra `NEXT_STATE_MAP` en la línea 111. Es puramente una lista blanca de "estados a los que un transportista puede llegar alguna vez" — no está atada a `NEXT_STATE_MAP` por código, solo por convención manual. Si alguien agrega un nuevo estado alcanzable por transportista en `NEXT_STATE_MAP` sin tocar esta constante, la API lo rechazará silenciosamente con un 400 aunque la transición sea válida según la lógica web. Es una **tercera fuente de verdad que puede divergir sin que ningún test lo detecte** (no hay tests, ver punto 2).

**Nota**: el filtrado de `cerrada` para transportistas está implementado dos veces con lógica distinta:
- Web: `guides/views.py:372-373` filtra la lista de tuplas después de construir `next_states`.
- API: `guides/api/serializers.py:117-124` (`get_proximos_estados`) hace lo mismo pero solo afecta lo que se **muestra** en el serializer, no lo que se **permite** en `UpdateEstadoView` — ahí la restricción real viene de `ESTADOS_VALIDOS_TRANSPORTISTA` (que ya excluye `'cerrada'` porque no está en el set).

**Recomendación**: centralizar en un solo módulo (p. ej. `guides/state_machine.py`) importado por `views.py`, `api/serializers.py` y `api/views.py`, derivando `ESTADOS_VALIDOS_TRANSPORTISTA` de `NEXT_STATE_MAP` (`{s for transitions in NEXT_STATE_MAP.values() for s in transitions} - {'cerrada'}`) en vez de mantenerlo como lista manual.

---

## 2. Cobertura de tests

`guides/tests.py:1-3` confirmado vacío (solo el boilerplate `from django.test import TestCase`), y `git log --oneline -- guides/tests.py` muestra un único commit (`83f5301`, el scaffold inicial del proyecto) — nunca se ha tocado desde entonces. `python manage.py test` no ejecuta ninguna prueba real hoy.

Las 5 rutas de código más críticas para priorizar tests, en orden de riesgo:

1. **Transición de estado + validación de foto obligatoria** (`guides/views.py:375-415` y `guides/api/views.py:90-169`). Es el corazón del flujo de negocio y está duplicado en dos capas (ver punto 1); un cambio en una sin test que cubra la otra rompe la paridad web/API sin aviso.
2. **`_process_sheet` (importador Excel)** (`guides/views.py:719-940`). Maneja dinero/inventario real (guías del ERP), tiene lógica de matching difuso (`raw_lower in nombre_lower or nombre_lower in raw_lower`, `views.py:822`) que puede producir falsos positivos silenciosos al asignar vendedor/transportista, y usa `bulk_create`/`bulk_update` fuera de una transacción explícita — un fallo a mitad de archivo deja datos parcialmente importados.
3. **`generate_guide_pdf_backup`** (`guides/services.py:46-83`). Es la única vía por la que se genera y adjunta el respaldo legal ("nota de venta firmada"); un fallo silencioso (ver punto 3) significa que el cliente/coordinador nunca recibe el PDF y nadie se entera.
4. **`send_seller_notification` / `send_coordinator_notification`** (`guides/services.py:216-313`). Falla completamente en silencio si Mandrill no está configurado o rechaza destinatarios (punto 3); sin test, una regresión (p. ej. cambio de firma de `_build_email_body`) pasaría inadvertida hasta que un vendedor reporte "nunca me llegó el correo".
5. **Permisos por rol** (`guides/decorators.py`, `guides/api/permissions.py::IsTransportista`, `guides/utils.py`). Son la única barrera entre roles (no hay modelo de usuario custom); un test que verifique que un transportista no puede acceder a `guide_list`/`import_guides_excel`/`delete_guide` ni a guías ajenas vía API (`GuiaDetailView.get_queryset`, `api/views.py:77-82`, filtra por `transportista=self.request.user` pero solo se prueba manualmente hoy) es la red de seguridad más barata de escribir.

**Recomendación**: empezar por (1) y (5) — son los de mayor blast radius y los más baratos de testear con `Client()`/`APIClient()` de Django/DRF sin mocks complejos.

---

## 3. Manejo de errores silenciosos

Inventario de todos los `try/except` que hacen catch-and-log sin propagar:

| Función | Archivo:línea | Qué atrapa | Efecto si falla |
|---|---|---|---|
| `_generate_pdf_bytes` (vía `generate_guide_pdf_backup`) | `guides/services.py:56-60` | Cualquier excepción de Pillow al abrir/convertir la imagen | Log `logger.error(...)`, retorna `(None, None)`. El correo se envía **sin PDF adjunto** y sin que nadie lo note salvo leyendo logs de Render. |
| Subida a Cloudinary del PDF | `guides/services.py:73-83` | Cualquier excepción de `cloudinary.uploader.upload` | Log `logger.error(...)`, retorna `(pdf_bytes, None)`. El PDF se adjunta al correo (porque `pdf_bytes` sí se generó) pero **no queda respaldo en `GuideStagePhoto.pdf_backup`** — no hay forma de re-descargarlo después. |
| `_send_message` (usado por ambas notificaciones) | `guides/services.py:191-198` | Excepción de red/API de Mandrill | Log `logger.error(...)`, retorna `False`. Ni el vendedor ni el coordinador se enteran. |
| `_send_message` — rechazo por destinatario | `guides/services.py:200-211` | No es una excepción; Mandrill responde 200 pero marca el destinatario como rechazado (bounce, blacklist) | Log `logger.warning(...)` por destinatario, pero la función global igual puede devolver `True` si *otro* destinatario sí recibió el correo — el remitente cree que todo salió bien. |
| `send_seller_notification` sin `vendedor.email` | `guides/services.py:225-230` | No hay email de vendedor configurado | Log `logger.warning(...)`, `return` silencioso — el vendedor simplemente nunca es notificado, y no hay ningún indicador visible en la UI del estado de la guía. |
| `send_seller_notification`/`send_coordinator_notification` sin Mandrill configurado | `guides/services.py:233-238, 286-291` | Faltan `MANDRILL_API_KEY`/`MANDRILL_FROM_EMAIL` | Log `logger.warning(...)` — si en algún momento se borra la env var en Render por error, **todas** las notificaciones dejan de enviarse sin ningún error visible fuera de los logs. |
| `foto.storage.delete(foto.name)` al borrar guía | `guides/views.py:1059-1063` | Cualquier excepción al borrar el archivo del storage | `except Exception: pass` — ni siquiera hay log. Archivos huérfanos en Cloudinary/filesystem se acumulan sin rastro. |
| `_build_email_body` — obtención de URL de foto | `guides/services.py:100-109` | Excepción al resolver `foto_obj.foto.url` | `except Exception: pass` — la foto simplemente no aparece en el correo, sin log. |
| API `GuideStagePhotoSerializer.get_url` / `GuideStageSerializer.get_foto_legacy` | `guides/api/serializers.py:32-36, 54-58` | Excepción al resolver URL de storage | Retorna `None` silenciosamente — la app móvil vería una foto sin URL sin que el backend deje rastro. |

**Mecanismo de alerta/monitoreo**: no existe ninguno. Se confirmó por grep (`sentry|rollbar|honeybadger|bugsnag|datadog|newrelic`) que no hay integración de error tracking en `requirements.txt` ni en el código. El único canal es `tracking_guide/settings.py:159-182` (`LOGGING`), que envía todo a `console`/stdout con nivel `WARNING` — Render captura esos logs, pero **nadie los lee de forma proactiva**: no hay alerta push, email, ni dashboard de errores. Un fallo de Mandrill o Cloudinary que dure días pasaría completamente desapercibido salvo que un usuario reclame directamente.

**Recomendación**: agregar Sentry (o similar) con el DSN como env var — es un cambio de bajo esfuerzo (SDK + una línea en `settings.py`) que convierte estos `logger.error`/`logger.warning` en alertas accionables sin cambiar la lógica de "no fatal" que el negocio ya decidió (correctamente: un fallo de email no debe bloquear el flujo del transportista).

---

## 4. Storage condicionado por DEBUG

`tracking_guide/settings.py:128-139`:
```python
STORAGES = {
    'default': {
        'BACKEND': (
            'django.core.files.storage.FileSystemStorage'
            if DEBUG else
            'cloudinary_storage.storage.MediaCloudinaryStorage'
        ),
    },
    ...
}
```
Confirmado: depende **exclusivamente** de `DEBUG` (booleano derivado de la env var `DEBUG` en `settings.py:16`, `os.environ.get('DEBUG', 'False') == 'True'`). Lo mismo aplica al storage de PDFs en `guides/models.py:31-38` (`_pdf_storage()`) y a la subida de respaldo en `guides/services.py:62-63` (`if settings.DEBUG: return pdf_bytes, None`).

**Qué pasa si `DEBUG=True` se activa por error en producción (Render)**:
- `render.yaml:10-11` fija `DEBUG` a `"False"` explícitamente para el servicio web, y `render.yaml:32-33` igual para el cron. Así que un typo accidental requeriría editar el env var manualmente en el dashboard de Render, no es un riesgo de "default inseguro" — pero **si alguien lo cambia** (p. ej. para debug temporal de un incidente), el impacto es:
  1. Todas las fotos/PDFs subidos en ese lapso van a `FileSystemStorage` (`MEDIA_ROOT = BASE_DIR / 'media'`, `settings.py:122`), es decir al filesystem local del dyno de Render, **no** a Cloudinary.
  2. El filesystem de un servicio web de Render (`env: python`, sin disco persistente declarado en `render.yaml`) es **efímero**: se pierde en cada deploy y, dependiendo del plan, también en reinicios/reescalado del proceso. `render.yaml` no declara ningún bloque `disk:` para el servicio `tracking-guide`, así que no hay persistencia configurada.
  3. Además, con `DEBUG=True` Django expone tracebacks completos (incluyendo `SECRET_KEY` si se genera con `generateValue: true` y aparece en un stack, o rutas internas) a cualquier visitante que provoque un error 500 — riesgo de seguridad adicional, no solo de storage.
  4. Adicionalmente, `SECURE_PROXY_SSL_HEADER`, `CSRF_COOKIE_SECURE`, `SESSION_COOKIE_SECURE` (`settings.py:33-37`) también están atados a `not DEBUG` — con `DEBUG=True` las cookies dejan de forzar `Secure`, otra superficie de riesgo si ocurre en prod.

**Recomendación**: no depender de `DEBUG` para decidir storage/seguridad de cookies. Introducir una env var explícita (`USE_CLOUDINARY` o derivarla de `ENVIRONMENT=production/development`) para que un `DEBUG=True` temporal en producción (útil para diagnosticar un 500) no tenga como efecto secundario escribir archivos a un disco efímero y perder evidencia fotográfica de entregas.

---

## 5. Dependencias: requirements.txt vs pyproject.toml/uv.lock

`render.yaml:5,27` usa `pip install -r requirements.txt` en ambos servicios (web y cron) — **`pyproject.toml`/`uv.lock` no se usan en el deploy real**, confirmando lo que ya dice `CLAUDE.md`.

Divergencias encontradas:

| Paquete | `requirements.txt` | `uv.lock` | Nota |
|---|---|---|---|
| Django | `5.2.14` (`requirements.txt:2`) | `5.2.15` **y** `6.0.6` (dos entradas, `uv.lock` líneas con `resolution-markers` distintos para `python_full_version < '3.12'` vs `>= '3.12'`) | `uv.lock` ni siquiera resuelve a una sola versión de Django — apunta a Django 6 en Python ≥3.12, un major distinto al que corre en producción. |
| djangorestframework | `3.16.0` (`requirements.txt:21`) | `3.17.1` | Versión menor distinta; no crítico pero confirma que el lock no refleja lo instalado. |
| Contenido de `pyproject.toml` | — | `dependencies = ["django-rest-framework>=0.1.0", "openpyxl>=3.1.5", "packages>=0.1.1"]` (`pyproject.toml:7-11`) | `django-rest-framework` (con guion) **no es el paquete real** de PyPI — el paquete correcto es `djangorestframework` (sin guiones, ver `requirements.txt:21`). El nombre con guion sí existe en PyPI pero es un paquete distinto/no relacionado. `packages>=0.1.1` tampoco es una dependencia real del proyecto (parece un placeholder o error de tipeo). Ni Django ni Pillow ni gunicorn ni cloudinary aparecen como dependencias directas en `pyproject.toml`, solo llegan transitivamente vía `uv.lock`. |

**Riesgo concreto**: si alguien ejecuta `uv sync` o `pip install -e .` confiando en `pyproject.toml` para levantar un entorno "limpio" (algo razonable dado que es el archivo más moderno), terminará con Django 6.x o con el paquete incorrecto `django-rest-framework`, ambos incompatibles con el código actual (p. ej. `STORAGES` dict-based settings, cambios de comportamiento entre Django 5 y 6). Es una trampa real para onboarding.

**Recomendación**: o se elimina `pyproject.toml`/`uv.lock` (si no se usan y generan confusión), o se regeneran a partir de `requirements.txt` como fuente de verdad única, dejando claro en un comentario cuál es la fuente autoritativa (CLAUDE.md ya lo aclara, pero el propio repo no lo hace).

---

## 6. Vendedor: FK (`Seller`) vs texto libre (`vendedor_nombre`)

`get_vendedor_display()` (`guides/models.py:105-110`):
```python
def get_vendedor_display(self):
    if self.vendedor_nombre:
        return self.vendedor_nombre
    if self.vendedor:
        return self.vendedor.nombre
    return 'Sin vendedor asignado'
```
`vendedor_nombre` tiene prioridad sobre la FK `vendedor` cuando ambos están presentes.

**Flujo manual — `create_guide`** (`guides/views.py:298-299`):
```python
if not admin_session:
    guide.vendedor_nombre = None
```
Si quien crea la guía **no** es admin/coordinador, se fuerza `vendedor_nombre = None` explícitamente antes de guardar, aunque el formulario tenga el campo oculto (`guides/forms.py:85`, `self.fields['vendedor_nombre'].widget = forms.HiddenInput()` — oculto pero no deshabilitado, así que un POST manual podría inyectar un valor que la vista luego pisa a `None`). Es una limpieza **defensiva y explícita en la vista**, independiente del formulario.

**Flujo de importación Excel — `_process_sheet`** (`guides/views.py:817-826`):
```python
creado_por_raw = str(get('creado_por') or '').strip()
vendedor_obj = vendedor_nombre = None
if creado_por_raw:
    raw_lower = creado_por_raw.lower()
    for nombre_lower, v in vendedores_map.items():
        if raw_lower in nombre_lower or nombre_lower in raw_lower:
            vendedor_obj = v
            break
    if not vendedor_obj:
        vendedor_nombre = creado_por_raw
```
Aquí `vendedor_nombre` se llena **solo si no hay match** contra `Seller` (matching difuso por substring, no exacto — riesgo aparte: `"ana"` matchea contra `"Ana María Soto"` y viceversa). No hay ningún control de si quien ejecuta la importación es admin/coordinador (la vista ya está gateada por `@admin_or_coordinador_required`, `guides/views.py:943`) — pero a diferencia del flujo manual, **no hay lógica que fuerce `vendedor_nombre = None`** porque conceptualmente aquí siempre corre con permisos de staff/coordinador.

**Conclusión**: no hay asimetría *incorrecta* — son dos contextos distintos con distinta necesidad (uno filtra por rol de quien crea, el otro parte de datos del ERP donde siempre hay contexto administrativo) — pero **sí hay asimetría de robustez**: el matching difuso de `creado_por_raw` en la importación (líneas 821-822, `raw_lower in nombre_lower or nombre_lower in raw_lower`) puede asignar el vendedor equivocado en silencio (sin quedar registrado en `errores`), mientras que el flujo manual usa un `ModelChoiceField` (`guides/forms.py:26-31`) que no permite error de match. Esto no está señalado en `CLAUDE.md`, que solo dice "no hay asimetría" implícitamente al describir ambos flujos por separado.

**Recomendación**: en `_process_sheet`, registrar en `errores`/`sin_link`-style warning cuando el match de vendedor es ambiguo (más de un `Seller` matchea) o parcial, para que quede visible en el resumen de importación en vez de asignarse silenciosamente.

---

## 7. CSRF exemption y autenticación de `/api/`

`tracking_guide/middleware.py:17-20` marca `csrf_processing_done = True` para **todo** path bajo `/api/`, sin distinción de vista.

Verificación de autenticación real por endpoint (`guides/api/urls.py:1-15`, `guides/api/views.py`):

| Endpoint | Vista | `permission_classes` / auth |
|---|---|---|
| `/api/v1/auth/login/` | `LoginView(TokenObtainPairView)` (`api/views.py:33-34`) | Sin `permission_classes` propio → usa el default global `IsAuthenticated` de DRF, pero `TokenObtainPairView` es de acceso público por diseño (login). No usa sesión. |
| `/api/v1/auth/refresh/` | `TokenRefreshView` (importado directo de `simplejwt`, `api/urls.py:2,8`) | Público, basado en refresh token JWT, no sesión. |
| `/api/v1/auth/me/` | `MeView` (`api/views.py:39-40`) | `permission_classes = [IsTransportista]` |
| `/api/v1/mis-guias/` | `MisGuiasView` (`api/views.py:54-56`) | `permission_classes = [IsTransportista]` |
| `/api/v1/guias/<pk>/` | `GuiaDetailView` (`api/views.py:73-75`) | `permission_classes = [IsTransportista]` |
| `/api/v1/guias/<pk>/estado/` | `UpdateEstadoView` (`api/views.py:87-88`) | `permission_classes = [IsTransportista]` |

`IsTransportista` (`guides/api/permissions.py:4-12`) valida `request.user.is_authenticated` — y como `REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES']` (`settings.py:188-190`) contiene **únicamente** `JWTAuthentication`, ese `is_authenticated` solo puede ser `True` vía un JWT válido, nunca vía cookie de sesión.

Se confirmó por grep (`SessionAuthentication|authentication_classes`) que **ningún archivo** bajo `guides/api/` ni `tracking_guide/` referencia `SessionAuthentication` ni sobreescribe `authentication_classes` a nivel de vista. **No hay ningún endpoint bajo `/api/` que dependa de sesión/cookies.**

**Estado**: descartado como riesgo — el diseño es correcto y el comentario en `middleware.py:5-12` describe fielmente el comportamiento actual.

---

## 8. Cron de cierre automático

`render.yaml:23-37` define el servicio `type: cron`, `schedule: "0 * * * *"` (cada hora), ejecutando `python manage.py cerrar_guias_vencidas`.

`guides/management/commands/cerrar_guias_vencidas.py:16-36`:
```python
def handle(self, *args, **options):
    limite = timezone.now() - timezone.timedelta(hours=24)
    guias = DispatchGuide.objects.filter(estado__in=ESTADOS_CERRABLES, fecha_creacion__lte=limite)
    cerradas = 0
    for guia in guias.iterator():
        with transaction.atomic():
            GuideStage.objects.create(...)
            guia.estado = 'cerrada'
            guia.save(update_fields=['estado', 'fecha_actualizacion'])
        cerradas += 1
    self.stdout.write(self.style.SUCCESS(f'{cerradas} guía(s) cerrada(s) automáticamente.'))
```

**Logging de ejecución**: solo hay un `self.stdout.write(self.style.SUCCESS(...))` al final, que va a stdout (capturado por Render, visible en sus logs) — **no hay ningún log si la ejecución falla antes de llegar a esa línea** (excepción no capturada explícitamente: si `guias.iterator()` o el `save()` lanzan, el comando termina con traceback + exit code ≠ 0, pero eso solo se ve si alguien entra manualmente a revisar el log del cron job en el dashboard de Render). Tampoco hay ningún log de "inicio de ejecución" — si el cron simplemente no corre (falla del scheduler, cambio de config, servicio pausado), no queda ningún rastro comparativo ("se esperaba 1 corrida a las 14:00 y no ocurrió").

**Mecanismo de detección de cron caído**: ninguno. No hay heartbeat, no hay ping a un servicio externo (p. ej. Healthchecks.io/Cronitor), y como se estableció en el punto 3, no hay Sentry ni similar que capture excepciones no manejadas del comando.

**Riesgo real**: bajo/medio en términos de negocio (el cierre automático es housekeeping — si no corre, las guías `entregada`/`rechazada` simplemente quedan visibles más tiempo de lo esperado en el listado operativo en vez de pasar a `closed_guides`; no hay pérdida de datos), pero **alto en observabilidad** — nadie se enteraría de un fallo silencioso hasta notar manualmente que el listado de guías activas está más poblado de lo normal.

**Recomendación** (quick win, ver abajo): agregar 2-3 líneas de logging explícito al inicio/fin del comando vía el logger `guides` ya configurado en `settings.py:175-181`, y opcionalmente un ping HTTP a un servicio de heartbeat gratuito al final del `handle()`.

---

## 9. Campo legado `GuideStage.foto`

`CLAUDE.md` dice: *"la newer, category-tagged... model; the API and current web flow use this instead of `GuideStage.foto`"*, dando a entender que `foto` es puramente legado/no usado en flujos activos. **Esto es documentación desactualizada** — el campo sigue activo en varios lugares:

- **Templates web** (`guides/templates/guides/guide_detail.html:561-563` y `guides/templates/guides/transportista_guide_detail.html:555-557`): ambos templates tienen un `{% elif stage.foto %}` como fallback de visualización cuando la etapa no tiene fotos en `GuideStagePhoto` — es decir, **sigue siendo leído activamente en la UI** para mostrar registros antiguos.
- **API** (`guides/api/serializers.py:43,49-58`): `GuideStageSerializer.foto_legacy` expone explícitamente `obj.foto.url` bajo el campo `foto_legacy` en cada respuesta de etapa — la app móvil lo recibe en cada `GET` de detalle de guía.
- **Correos** (`guides/services.py:105-109`): `_build_email_body` incluye `stage.foto` en la lista de `foto_urls` del email de notificación si está presente.
- **Escritura activa**: `guides/views.py:303-308`, en `create_guide`, **todavía escribe** `GuideStage.objects.create(..., foto=form.cleaned_data.get('foto_emision'), ...)` — el campo `foto` legado se sigue poblando hoy en el flujo de creación de guía (etapa inicial `'emitida'`), no solo se lee por compatibilidad histórica.
- **Admin** (`guides/admin.py:12`, `GuideStageInline.fields`) también expone `foto` como campo editable.

**Conclusión**: `GuideStage.foto` no es código muerto — es un campo con doble propósito: (a) sigue siendo el único lugar donde se guarda la foto de la etapa `'emitida'` (creación de guía, que no pasa por `GuideStagePhoto` en absoluto — ver `views.py:303-308`, no hay ningún `GuideStagePhoto.objects.create` en `create_guide`), y (b) fallback legado para etapas antiguas en `entregada`/`rechazada`. La frase de `CLAUDE.md` que sugiere que fue reemplazado del todo es inexacta.

**Recomendación**: si la intención de producto es que `GuideStagePhoto` sea el modelo único, migrar `create_guide` para usar también `GuideStagePhoto` con `categoria='general'` (o una nueva categoría `'emision'`) en vez de `GuideStage.foto`, y luego sí se podría considerar deprecar el campo legado. Mientras tanto, actualizar `CLAUDE.md` para reflejar que `foto` sigue en uso activo para la etapa de emisión.

---

## 10. Performance de `transportista_report`

`guides/views.py:436-534`. El cálculo de promedio `en_ruta → entregada/rechazada` es efectivamente Python puro sobre datos ya traídos a memoria, **no** una agregación SQL:

```python
guides_qs = DispatchGuide.objects.filter(transportista__isnull=False)...prefetch_related(
    Prefetch('etapas', queryset=GuideStage.objects.order_by('timestamp'))
)
...
for guide in guides_qs:              # views.py:461
    ...
    etapas = list(guide.etapas.all())          # views.py:491 — usa el prefetch, no dispara query nueva
    etapa_en_ruta = next((e for e in etapas if e.estado == 'en_ruta'), None)   # views.py:492
    etapa_final = next((e for e in etapas if e.estado in ('entregada', 'rechazada')), None)  # views.py:493
    if etapa_en_ruta and etapa_final:
        segundos = (etapa_final.timestamp - etapa_en_ruta.timestamp).total_seconds()
```

**Patrón de queries**: gracias al `Prefetch('etapas', ...)` (`views.py:444`) **no hay N+1** — es 1 query para las guías + 1 query para todas sus etapas (2 queries totales, independiente del número de transportistas/guías). Esto es correcto y evita el problema más común. Lo que sí es ineficiente es que:
1. Trae **todas** las `GuideStage` de **todas** las guías con transportista asignado a memoria de Python, incluso cuando solo se necesitan dos timestamps por guía (`en_ruta` y `entregada`/`rechazada`) — con `GuideStage.STATUS_CHOICES` teniendo 6 estados posibles, se cargan también etapas irrelevantes (`emitida`, `asignada`, `cerrada`).
2. El promedio, mínimo y máximo (`fmt_time`, `views.py:499-502` y agregación en `views.py:508-511`) se calculan sobre listas Python (`sum(tiempos)/len(tiempos)`, `min(tiempos)`, `max(tiempos)`) en vez de vía SQL (`Avg`, `Min`, `Max` de Django con una expresión de diferencia de timestamps, factible desde Django 4.2+ con `ExpressionWrapper` + `F() - F()` sobre subqueries).

**Volumen en la DB accesible**: la base local (`db.sqlite3`, 196 KB) está **vacía** (`DispatchGuide.objects.count() == 0`, verificado vía shell) — es un entorno de desarrollo limpio, no refleja producción. No fue posible medir el volumen real de producción desde este entorno.

**Estimación de impacto sin datos reales**: con el patrón actual (2 queries fijas + trabajo O(guías × etapas_por_guía) en Python puro), el cuello de botella no es de queries (no hay N+1) sino de **memoria y CPU en el worker Gunicorn** al crecer el volumen — cargar, por ejemplo, decenas de miles de `GuideStage` en objetos Python y iterarlos con `next()` en cada guía es notablemente más lento que un `annotate` en SQL, pero no representaría un problema serio hasta volúmenes de varios miles de guías por consulta de reporte (el filtro por rango de fechas, `views.py:447-457`, ya acota el conjunto en la práctica). No es urgente hoy, pero **no escala linealmente bien** y es candidato a revisión si el reporte empieza a filtrarse sin rango de fechas sobre todo el histórico.

**Recomendación**: no es prioritario mientras el uso típico incluya rango de fechas. Si se detecta lentitud, la vía más simple no es reescribir a SQL puro sino **acotar el prefetch** a `GuideStage.objects.filter(estado__in=['en_ruta','entregada','rechazada']).order_by('timestamp')` para reducir el volumen de objetos Python cargados sin cambiar la lógica de negocio.

---

## Hallazgos adicionales fuera del checklist

- **Ausencia total de monitoreo/alerting** (Sentry o equivalente): es, en la práctica, el hallazgo más transversal de esta auditoría — subyace a los puntos 3 y 8, y probablemente a cualquier bug futuro en producción. Ver recomendación en Quick wins.
- **`GuideStagePhoto` no registrado en el admin** (`guides/admin.py:1-4`, el import solo trae `Client, DeletedGuideNumber, DispatchGuide, GuideStage, Seller`): el staff no puede ver/gestionar fotos individuales (categoría, `pdf_backup`) desde el admin de Django salvo navegando por la inline de `GuideStage`, que tampoco expone `GuideStagePhoto` (`GuideStageInline.fields`, `admin.py:12`, solo incluye el campo legado `foto`). No es grave pero limita la capacidad de soporte/debug manual vía admin.
- **`pyproject.toml` describe un paquete PyPI inexistente/incorrecto** (`django-rest-framework` en vez de `djangorestframework`, `pyproject.toml:8`) — ver punto 5.
- **Matching difuso de nombres en la importación Excel** (`guides/views.py:822,832-834`, substring bidireccional para vendedor y transportista) puede producir asignaciones incorrectas silenciosas con nombres cortos o ambiguos (p. ej. "Ana" vs "Mariana") — mencionado en el punto 6, pero aplica igual al matching de `transportista` en `views.py:828-836`.

---

## Quick wins (mayor impacto / menor esfuerzo)

1. **Agregar Sentry (o equivalente) con el DSN como env var.** Resuelve de raíz la falta de visibilidad de los puntos 3 y 8 (notificaciones, PDF, Cloudinary, cron) sin tocar la lógica de negocio "no fatal" ya decidida — es literalmente instalar el SDK y 3-4 líneas en `settings.py`. Es el cambio de mayor apalancamiento de toda la auditoría.
2. **Loggear inicio/fin (con conteo) de `cerrar_guias_vencidas`** vía el logger `guides` ya configurado (`settings.py:175-181`), y opcionalmente sumar un ping a un servicio de heartbeat gratuito (Healthchecks.io) al final de `handle()`. Con eso se detecta en minutos si el cron dejó de correr, hoy no hay forma de saberlo.
3. **Derivar `ESTADOS_VALIDOS_TRANSPORTISTA` de `NEXT_STATE_MAP`** en vez de mantenerlo como constante manual separada (`guides/api/views.py:28`) — una línea de cambio (`{s for v in NEXT_STATE_MAP.values() for s in v} - {'cerrada'}`) elimina permanentemente el riesgo de que ambas listas diverjan silenciosamente en un futuro cambio de workflow.
