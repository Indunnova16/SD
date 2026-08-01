# TRIAGE — SD#47 "Integrar portal de pago (WOMPI + Alegra) — suscripción del cliente"

**Fecha:** 2026-07-31
**Issue:** [Indunnova16/SD#47](https://github.com/Indunnova16/SD/issues/47)
**Modo:** F1(triage)→F2(diagnóstico)→F3(selfverify), `--no-deploy`, sin comentar/cerrar/asignar el issue (restricción de este ejercicio)
**Branch:** `feat/sd-47` (worktree `SD_wt_47`, sobre `origin/main` @ `e2d3634`)
**Veredicto F1: ✅ YA RESUELTO — este issue es un duplicado histórico de #85, que está 100% implementado y desplegado a prod.**

## F1 — Triage

Al leer el issue completo (`gh issue view 47 --comments`) aparece un comentario
propio (2026-07-29) que ya documenta lo esencial:

> "Investigación de Desarrollo/TI (2026-07-29): este issue se cerró el mismo
> día que se creó (2026-06-09), sin comentarios ni evidencia de
> implementación [...] El alcance real queda formalizado en **#85** [...] el
> trabajo continúa en #85."

Es decir: #47 fue el issue original, cerrado sin evidencia el mismo día por
confusión de repos (coincide en fecha exacta con el port del mismo módulo a
`Datainnovation`, commit `860aa7b`). El propio Desarrollo/TI ya reabrió el
hilo, constató que SD seguía sin nada de pagos en ese momento, y formalizó el
alcance real en #85 — con el gap de arquitectura Django 4.2→5.1 documentado
(SD es cookiecutter-django, `AUTH_USER_MODEL=accounts.User`, RBAC propio; la
fuente `pagos-template`/Obraje/Fundiciones corre Django 4.2 plano).

**Estado real de #85 (verificado con `gh issue view 85 --comments`):**

- Comentario 2026-07-30 10:21 — "🟡 Sprint A completo y validado en prod":
  11/11 sub-items del Sprint A (modelos, wompi.py/alegra.py, vistas+RBAC,
  settings con defaults seguros, wiring urls, templates DaisyUI + navbar
  desktop+mobile, CSP, tests adaptados a `accounts.User`, tests RBAC,
  `crear_plan`). 34/34 tests nuevos en verde, full-repo 1639 passed/1
  skipped/0 failed en ese momento. 5/5 journeys E2E reales contra prod.
- Comentario 2026-07-30 11:20 — "🟢 Sprint B completado": 6 secretos
  WOMPI/Alegra reales provisionados en GCP Secret Manager, deploy con
  `WOMPI_SANDBOX=False`, widget WOMPI verificado con `data-public-key` real
  vía E2E, `SD` registrado en el `wompi-router` compartido. Único pendiente
  declarado: precio real de la suscripción (hoy placeholder $150.000) — una
  decisión comercial explícitamente fuera del repo (la nota de #47 ya lo
  aclaraba: *"El valor y la gestión del cobro con el cliente se coordinan
  por fuera del repo, tarea de NOVA IA"*).

**Checklist original de #47, verificado contra el estado real de `main`
(`e2d3634`) en este triage:**

| Ítem del checklist de #47 | Estado verificado |
|---|---|
| Copiar la app `pagos/` y adaptarla al stack | ✅ `pagos/` existe en raíz (models, admin, apps, wompi.py, alegra.py, views.py, urls.py, context_processors.py, management/commands/crear_plan.py) |
| Registrar en `INSTALLED_APPS` + `pagos.urls` + context_processor | ✅ `config/settings/base.py:70` (`"pagos"`), `:105` (`pagos.context_processors.alertas_pago`), `config/urls.py:73` |
| Migraciones aplicadas (legacy-safe) | ✅ `0001_initial.py` + `0002_pago_n_meses.py`; `makemigrations pagos --check --dry-run` → "No changes detected"; desplegadas en prod (revisión `sd-lms-00093-dcl`, 100% tráfico, per #85) |
| Secrets WOMPI + Alegra cableados | ✅ `config/settings/base.py` bloque `WOMPI_*`/`ALEGRA_*` vía `config()` con `default=""` seguro; 6 secrets reales en GCP Secret Manager (Sprint B, #85) — **no verificado por mí, no toco prod** |
| Webhook WOMPI (firma + idempotencia) | ✅ `WompiWebhookView.post` valida `wompi.verify_webhook_signature` (HMAC-SHA256, `hmac.compare_digest`) antes de procesar, y usa `get_or_create` + flag `ya_estaba_aprobado` para no duplicar el avance de `fecha_proximo_pago`/factura Alegra en reintentos del webhook. Cubierto por tests (`test_issue_2.py` "Gap #5 -- idempotencia del webhook") |
| `crear_plan_<cliente>` | ✅ `pagos/management/commands/crear_plan.py`, ya corrido en prod (precio placeholder, pendiente cifra real — fuera de scope de repo) |
| Smoke prod completo | ✅ 5/5 journeys E2E Playwright reales contra prod (#85, comentario Sprint A) |
| Portal visible solo para el rol que paga | ✅ Las 3 vistas (`PagoPortalView`, `DatosFacturacionView`, `HistorialPagosView`) usan `RolRequiredMixin(allowed_roles=(Rol.ADMINISTRADOR,))`; `pagos/tests/test_rbac_gating.py` cubre ADMINISTRADOR→200 y EJECUTOR/COORDINADOR→redirect |

**Además**, `git log` muestra que el módulo se extendió más allá del alcance
original de #47 vía **#92** ("clientes atrasados >1 mes solo podían pagar 1
mes"), ya mergeado a `main` (commits `542f6ba`, `470b4be`, `32564b0`,
`1ab6f74`): selector de N meses, grilla de 6 meses, `Pago.n_meses`,
`Suscripcion.meses_atraso`. Es decir, el módulo no solo está completo — está
un sprint más adelante del pedido original.

**Conclusión F1:** no hay backbone que construir. Construir uno nuevo sería
shotgun/duplicado — arriesga colisión de modelos (`PlanServicio`,
`Suscripcion`, `Pago`, `DatosFacturacion` ya existen), URLs (`pagos:portal`
ya registrado) y datos en prod (`PlanServicio` real ya creado). El único
gap declarado (precio real de la suscripción) es una decisión de negocio,
no una tarea de código, y ya está explícitamente fuera del scope original
de #47.

## F2 — Diagnóstico (arquitectura actual, para trazabilidad)

- **Modelos** (`pagos/models.py`): `PlanServicio` (nombre/precio/activo),
  `DatosFacturacion` (persona/identificación/régimen DIAN + `alegra_contacto_id`
  cacheado), `Suscripcion` (single-tenant — `Suscripcion.objects.first()`, sin
  FK a usuario — es facturación a nivel de toda la organización cliente, no
  por usuario), `Pago` (con `UniqueConstraint` en `wompi_reference` y
  `wompi_transaction_id` no vacíos — previene duplicados a nivel de BD, no
  solo de aplicación).
- **Integraciones** (`pagos/wompi.py`, `pagos/alegra.py`): clientes HTTP
  config-driven 100% vía `settings.WOMPI_*`/`settings.ALEGRA_*` (sin
  credenciales hardcodeadas en código en ningún punto — confirmado por
  lectura completa de ambos archivos). Firma de integridad WOMPI
  (`hashlib.sha256`) generada por request con timestamp de microsegundos
  (evita colisión de referencia entre intentos).
- **Vistas** (`pagos/views.py`): 3 vistas gateadas por rol ADMINISTRADOR +
  1 webhook público (`WompiWebhookView`, `csrf_exempt`, autenticidad vía
  firma HMAC, no sesión).
- **Riesgo de negocio explícito ya documentado en el propio código**: Alegra
  es cuenta compartida de **producción real**, sin sandbox distinguible —
  por eso el E2E de #85 no disparó `generar_factura_desde_pago` real, y por
  la misma razón yo tampoco la ejercito en este triage.

## F3 — Self-verify (sin cambios de código de producto)

Corrido en el worktree `SD_wt_47` (branch `feat/sd-47`, sin tocar `main`),
`DJANGO_SETTINGS_MODULE=config.settings.test` (SQLite in-memory, sin BD prod):

```
python manage.py check
  → System check identified no issues (0 silenced)

python manage.py makemigrations pagos --check --dry-run
  → No changes detected in app 'pagos'

python -m pytest pagos/ -q
  → 78 passed, 37 warnings in 10.00s
```

(El "FAIL Required test coverage of 60%" que imprime pytest es el gate
global `--cov=apps --cov-fail-under=60` de `pyproject.toml` — mide cobertura
de TODO `apps/`, no de `pagos/` (que vive en la raíz del repo, fuera de
`apps/`, por decisión de diseño documentada en `SPRINTS/PLAN_2026-07-29_
portal_pago_wompi_alegra.md`); es un artefacto de correr un subset, no una
regresión real. La suite completa (1639 passed/1 skipped/0 failed) ya se
corrió como parte del cierre de #85, sin cambios de código de producto desde
entonces que ameriten repetirla completa en este triage.)

No se hicieron llamadas reales a WOMPI/Alegra, no se tocaron secrets/prod,
no se generaron facturas Alegra reales.

## Qué NO se hizo (y por qué)

- **No se creó una implementación nueva/paralela del módulo `pagos/`** — ya
  existe, completa, en `main`, desplegada a prod. Hacerlo hubiera sido
  trabajo duplicado y riesgo de colisión.
- **No se comentó/asignó/cerró #47 ni #85 en GitHub** — restricción explícita
  de este ejercicio (protocolo normal de Indunnova pediría comentar #47
  señalando el duplicado y dejarlo asignado a Indunnova sin cerrar, ya que
  el cliente valida al cerrar; ese paso queda pendiente para cuando se
  autorice).
- **No se tocaron secrets ni BD de producción.**
- **No se hicieron llamadas reales a las APIs de WOMPI/Alegra** (sandbox o
  producción).

## Recomendación (para cuando se autorice tocar GitHub)

Comentar #47 remitiendo a #85 (ya completo y en prod) y a #92 (extensión ya
mergeada), sin cerrarlo — dejarlo asignado a Indunnova para que decida cerrar
como duplicado, siguiendo el protocolo de 7 pasos (no cerramos issues,
asignamos). El único pendiente de negocio real (precio final de la
suscripción, hoy placeholder $150.000 en `PlanServicio` de prod) no requiere
código — requiere la cifra comercial definitiva.
