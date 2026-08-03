# PLAN — Portal de pago WOMPI + facturación Alegra (issue #85)

**Fecha:** 2026-07-29
**Issue:** [Indunnova16/SD#85](https://github.com/Indunnova16/SD/issues/85) (retoma #47)
**Estado:** Planning completado, listo para ejecución

## Contexto

SD no tiene ningún módulo de pagos hoy (confirmado por grep: 0 archivos de
pago/wompi/alegra/suscripcion/billing). Se porta el módulo `pagos/` completo
(modelos `PlanServicio`/`DatosFacturacion`/`Suscripcion`/`Pago` + integración
WOMPI checkout+webhook + facturación electrónica DIAN vía Alegra) desde
`Indunnova16/pagos-template@19ee475` (`origin/main`, PR#3 mergeado — YA
incluye el hardening de 5 gaps de `pagos-template#2`: referencia WOMPI con
microsegundos, `fecha_proximo_pago`/`requiere_pago`, gate dinámico del
portal, `UniqueConstraint` doble en `Pago`, idempotencia del webhook).

SD es Django ≥5.1,<5.2 con cookiecutter-django (`config/settings/{base,
local,production,cloudrun}.py` split), `AUTH_USER_MODEL=accounts.User`
(`USERNAME_FIELD=document_number`, sin campo `username`), `django-allauth`,
DaisyUI 4.10.1 + Tailwind CDN, y un sistema RBAC real (`User.rol` ∈
{EJECUTOR, COORDINADOR, ADMINISTRADOR} — issue #58, `apps/accounts/
permissions.py` expone `RolRequiredMixin`/`require_rol`/`user_has_rol`). La
fuente (`pagos-template`) es Django 4.2, `settings.py` único, sin ningún
concepto de rol (solo `LoginRequiredMixin`) — es la primera vez que este
módulo se combina con Django 5.1 en el portafolio.

**Decisión de diseño (F2, no bloqueante):** el portal de pagos es
facturación/suscripción a nivel de TODA la organización cliente (single-
tenant: `Suscripcion.objects.first()`, no hay "suscripción por usuario"), no
una función operativa de EJECUTOR/COORDINADOR. Se gatean las 3 vistas
autenticadas (`PagoPortalView`, `DatosFacturacionView`, `HistorialPagosView`)
con `RolRequiredMixin(allowed_roles=(Rol.ADMINISTRADOR,))`, reusando el
mecanismo RBAC ya existente de SD en vez de dejarlas abiertas a cualquier
usuario logueado (comportamiento de la fuente). `WompiWebhookView` queda SIN
gate de sesión (correcto: es un endpoint público, la autenticidad la da la
firma HMAC `WOMPI_EVENTS_KEY`, exactamente como en la fuente).

**App top-level `pagos/` (no `apps/pagos/`):** decisión de mínimo riesgo —
la fuente importa `from pagos.models import ...` en todo el código y en los
tests; moverlo a `apps/pagos/` exige renombrar todos esos imports sin
beneficio funcional. Rompe la convención visual de "todo bajo `apps.`" que
siguen los otros 16 apps de SD, aceptado conscientemente.

## Sub-items por sprint

### Sprint A — código v1.0 (deployable como conjunto)

| # | Sub-item | Archivos | Tests | Dependencias | Complexity | Estado |
|---|---|---|---|---|---|---|
| A1 | Copiar `pagos/models.py` + `admin.py` + `apps.py` (+ `__init__.py`) verbatim desde `pagos-template@19ee475` — 0 adaptación (sin FK a `AUTH_USER_MODEL`, `Suscripcion` es single-tenant) | `pagos/__init__.py`, `pagos/models.py`, `pagos/admin.py`, `pagos/apps.py` | — | - | low | ⏳ pendiente |
| A2 | Copiar `pagos/wompi.py` + `pagos/alegra.py` verbatim — clientes API config-driven vía `settings.WOMPI_*`/`settings.ALEGRA_*` (resueltos en A5) | `pagos/wompi.py`, `pagos/alegra.py` | — | - | low | ⏳ pendiente |
| A3 | Copiar `pagos/views.py` + `pagos/urls.py`, agregando `RolRequiredMixin(allowed_roles=(Rol.ADMINISTRADOR,), redirect_url="reports:dashboard")` a `DatosFacturacionView`, `PagoPortalView`, `HistorialPagosView` (import `from apps.accounts.permissions import RolRequiredMixin` + `from apps.accounts.models import User; Rol = User.Rol`). `WompiWebhookView` SIN cambios. | `pagos/views.py`, `pagos/urls.py` | ver A9/A10 | A1 | medium | ⏳ pendiente |
| A4 | Generar `pagos/migrations/0001_initial.py` (`makemigrations pagos` contra Postgres local/Django 5.1 — el template no trae migraciones versionadas) | `pagos/migrations/0001_initial.py` (nuevo) | migración aplica limpio en local | A1 | low | ⏳ pendiente |
| A5 | Wiring `config/settings/base.py`: `LOCAL_APPS += ["pagos"]` + bloque `WOMPI_PUBLIC_KEY/PRIVATE_KEY/EVENTS_KEY/INTEGRITY_KEY/SANDBOX/REFERENCE_PREFIX`, `ALEGRA_EMAIL/API_TOKEN/API_URL/NUMBER_TEMPLATE_ID/ITEM_ID/BANK_ACCOUNT_ID`, `PAGOS_PLAN_NAME/PRICE/DESCRIPTION` vía `decouple.config(...)`. **CRÍTICO — TODAS con `default=""`/`default=0`/`default=True` (WOMPI_SANDBOX)**: sin default, `config()` revienta `UndefinedValueError` al importar `base.py`, lo que tumbaría el arranque de TODO SD (no solo `/pagos/`) el día que se despliegue esto ANTES de que existan los 6 GCP Secrets (Sprint B, bloqueado hoy) | `config/settings/base.py` | `manage.py check` sin error con env vacío | - | low | ⏳ pendiente |
| A6 | Wiring `config/urls.py`: `path("pagos/", include("pagos.urls", namespace="pagos"))` insertado en `urlpatterns` (después de la línea `feedback/`, antes del cierre `]` en la línea 73) | `config/urls.py` | - | A3 | trivial | ⏳ pendiente |
| A7 | Copiar `templates_daisyui/pagos/{portal,historial,datos_facturacion}.html` → `templates/pagos/` (set daisyUI confirmado correcto, NO bs5 — SD usa DaisyUI 4.10.1+Tailwind CDN, `templates/base.html` reexpone `{% block content %}` de `base/base.html`) **+** agregar el link `<a href="{% url 'pagos:portal' %}">💳 Portal de Pagos</a>` en LOS 2 SITIOS del bloque `{% if user.rol == 'ADMINISTRADOR' %}` de `templates/partials/navbar.html` (dropdown desktop L147-149, junto a "📊 Reportes y Analytics"; menú móvil L310-311) | `templates/pagos/portal.html`, `templates/pagos/historial.html`, `templates/pagos/datos_facturacion.html`, `templates/partials/navbar.html` | ver journey UI | A3 | medium | ⏳ pendiente |
| A8 | Wiring CSP (`config/settings/csp.py`): agregar `https://checkout.wompi.co` a `script-src` (widget de pago) y `https://api-colombia.com` a `connect-src` (fetch JS de departamentos/ciudades en `datos_facturacion.html`, ver `README.md` de la fuente). Hoy `CSP_ENFORCE=False` (report-only, `cloudrun.py`/`production.py`) — no rompe el smoke de este RUN, pero sin este wiring el flujo se rompería SILENCIOSAMENTE el día que SD active `CSP_ENFORCE=True` (exactamente el patrón que motivó SD#76, según el propio docstring de `csp.py`) | `config/settings/csp.py` | - | - | low | ⏳ pendiente |
| A9 | Adaptar `pagos/tests/test_issue_2.py`: reemplazar `from django.contrib.auth.models import User` (L21) + 3 sitios `User.objects.create_user(username=..., password=...)` (L159, L198, L330) por `get_user_model()` con campos reales de `accounts.User` (`document_number` como `USERNAME_FIELD`, `REQUIRED_FIELDS=[first_name,last_name,job_position,hire_date]`, sin `username`) — usar `force_login` donde sea posible para no fabricar `job_position`/`hire_date` innecesarios | `pagos/tests/test_issue_2.py` | 24 tests existentes (5 gaps del hardening) deben seguir en verde | A1, A3 | medium | ⏳ pendiente |
| A10 | Tests nuevos de gating RBAC (edge case real de SD, la fuente no lo cubre): usuario EJECUTOR/COORDINADOR → redirect fuera de `/pagos/`; usuario ADMINISTRADOR → 200. Cubre las 3 vistas gateadas de A3 | `pagos/tests/test_rbac_gating.py` (nuevo) | happy (ADMINISTRADOR accede) + 2 edge cases (EJECUTOR/COORDINADOR bloqueados) | A3, A9 | low | ⏳ pendiente |
| A11 | Copiar `pagos/management/commands/crear_plan.py` (+ `__init__.py`) verbatim — 0 cambios de código. La EJECUCIÓN contra prod con precio real es B1 (bloqueada) | `pagos/management/commands/__init__.py`, `pagos/management/commands/crear_plan.py` | - | A1 | trivial | ⏳ pendiente |

### Sprint B — bloqueado (input de Miguel / infraestructura compartida)

| # | Sub-item | Archivos | Dependencias | Complexity | Estado |
|---|---|---|---|---|---|
| B1 | Ejecutar `manage.py crear_plan` en prod con `PAGOS_PLAN_NAME/PRICE/DESCRIPTION` REALES (propuesta comercial ya enviada al cliente — la cifra no está en el issue, no inventar). Crea `PlanServicio` + `Suscripcion` en BD prod → **`accion_post_deploy`, `escribe_bd_prod: true`, `requiere_hitl: true`** | env / GCP Secret Manager (`PAGOS_PLAN_*`) | A11, B2 | trivial | ⏸ bloqueado — precio real |
| B2 | Provisionar 6 GCP Secrets (`sd-lms-wompi-public-key`, `-private-key`, `-events-key`, `-integrity-key`, `sd-lms-alegra-email`, `-api-token` — confirmado con `gcloud secrets list`: 0 de 85 secrets existentes matchean wompi/alegra) + agregarlos a `--set-secrets` del step "Deploy" de `.github/workflows/deploy.yml` (línea 66; los jobs `migrate`/`ensure-admin`/`axes-reset` NO los necesitan) | `.github/workflows/deploy.yml`, GCP Secret Manager (fuera del repo) | - | medium | ⏸ bloqueado — valores WOMPI/Alegra prod no provistos |
| B3 | Registrar `WOMPI_REFERENCE_PREFIX` único de SD (ej. `SDLMS`) en el `wompi-router` central — coordinación con administrador, fuera del repo (mismo mecanismo que ObrajeCRM/FundicionesMedellin/Datainnovation/SDCheckList) | wompi-router (fuera del repo) | - | low | ⏸ bloqueado — coordinación admin |

### Sprint C — validación

| # | Sub-item | Archivos | Dependencias | Complexity | Estado |
|---|---|---|---|---|---|
| C1 | Smoke E2E: portal gateado por rol (ADMINISTRADOR accede / EJECUTOR bloqueado) → plan+precio renderiza → widget WOMPI presente (public key no vacía) → datos de facturación persisten → historial lista pagos → webhook rechaza firma inválida (401). **NO** ejercita un cobro WOMPI sandbox real completo ni dispara `alegra.generar_factura_desde_pago` contra prod (ver Riesgos — Alegra es una cuenta compartida REAL, no hay sandbox distinguible; ese tramo queda cubierto por A9/A10, mocks) | — (Playwright contra prod) | Sprint A desplegado + B2 (al menos valores WOMPI para que el widget no renderice con `public key` vacía) | high | ⏳ pendiente |

## DAG dependencias

```
A1 → A3, A4, A9, A11
A3 → A6, A7, A9, A10
A5 → (independiente, requerido para que A2/A3 tengan settings resueltos en runtime)
A9 → A10
A8 → (independiente)
{A1..A11} → C1 (código desplegado)
B2 → C1 (validación completa del widget/webhook)
A11 + B2 → B1 (ejecución real)
```

## Riesgos y mitigaciones

- **Crash-on-boot si `WOMPI_*`/`ALEGRA_*` no llevan `default=` seguro en A5**
  (Sprint B bloqueado hoy → se va a desplegar Sprint A ANTES de que existan
  los 6 secrets). Mitigación: A5 usa `default=""` explícito en cada
  `config(...)`; el módulo queda "instalado pero inerte" — gateado además
  por rol ADMINISTRADOR, blast radius bajo si alguien lo visita sin
  secrets (error controlado al pedir la transacción/firma, no un 500 de
  arranque).
- **Alegra es cuenta compartida de PRODUCCIÓN, sin sandbox distinguible**
  (confirmado en `README.md` de la fuente: "mismos valores para todos los
  proyectos Indunnova"). El smoke E2E de prod (C1) NO debe disparar
  `generar_factura_desde_pago` real — crearía una factura electrónica DIAN
  real con datos de QA. Cobertura de esa lógica queda en A9/A10 (mocks,
  local/CI).
- **CSP (SD#76 — 3 capas de silencio ya documentadas en el repo).** A8
  agrega los 2 orígenes que la fuente necesita (`checkout.wompi.co`,
  `api-colombia.com`). Hoy `CSP_ENFORCE=False` así que no bloquea nada
  ahora, pero sin A8 el módulo queda con una bomba de tiempo idéntica a la
  que motivó SD#76 el día que se active enforce.
- **Sitios dispersos (riesgo_global alto → grep dirigido obligatorio,
  ver JSON `sitios_checklist`):** RolRequiredMixin en 3 clases de vista
  (A3) y el link de nav en 2 ubicaciones del navbar (A7, desktop+mobile) —
  patrón real de FIX_INCOMPLETO si se resuelve solo uno de los sitios.
- **Django 5.1 nunca antes probado con este módulo** en el portafolio
  (Obraje/Fundiciones/Datainnovation corren 4.2) — sin cambios de
  arquitectura anticipados (no hay FK a `AUTH_USER_MODEL` en el módulo),
  pero es la primera corrida real; C1 es `complexity_class: high` por eso.
- **wompi-router es infraestructura compartida** (B3) — alto radio de
  impacto si se configura mal (podría interferir con el enrutamiento de
  otros proyectos). `requiere_hitl: true`.
- **Precio real (B1) y secrets de producción (B2) son datos de negocio,
  no inventables** — quedan explícitamente bloqueados pidiendo el insumo a
  Miguel/Comercial, en vez de usar placeholders que luego se despliegan
  por error a prod.

## Validación esperada (smoke E2E — ver journey `SD_85.yaml`)

- `/pagos/` como ADMINISTRADOR (`qa_claude@indunnova.com`, confirmado
  `rol=ADMINISTRADOR` en BD prod) → 200, plan+precio+widget WOMPI visibles.
- `/pagos/` como EJECUTOR (`qa_ejecutor@indunnova.com`, confirmado
  `rol=EJECUTOR`) → redirigido fuera de `/pagos/` (gate RBAC).
- `/pagos/facturacion/` → formulario persiste datos de facturación
  (round-trip + cleanup).
- `/pagos/historial/` → 200, tabla de pagos (o estado vacío).
- `POST /pagos/webhook/` con firma inválida → 401 `invalid_signature`
  (sin necesidad de conocer `WOMPI_EVENTS_KEY` real — smoke de seguridad).
- Navbar: link "💳 Portal de Pagos" visible para ADMINISTRADOR.
