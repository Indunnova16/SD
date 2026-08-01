# PLAN — Fix atraso silencioso + pago de varios meses en /pagos/ (issue #92)

**Fecha:** 2026-07-30
**Issue:** [Indunnova16/SD#92](https://github.com/Indunnova16/SD/issues/92)
**Precedente:** [SD/SPRINTS/PLAN_2026-07-29_portal_pago_wompi_alegra.md](./PLAN_2026-07-29_portal_pago_wompi_alegra.md)
(issue #85 — port BASE del módulo `pagos/`, ya deployado en prod). Este plan
**NO duplica** el contexto de #85 (arquitectura RBAC, decisión single-tenant,
wiring CSP/settings/URLs) — se REFERENCIA. Léase primero si hace falta
contexto de por qué el módulo está armado como está.
**Estado:** Planning completado, listo para ejecución

## Contexto

Port de `pagos-template#11` (commit `f05a303`, mergeado) al módulo `pagos/`
de SD, ya en producción desde #85. Bug real confirmado en producción de
otros repos (FormasFuturo, ObrajeCRM): `_avanzar_fecha_proximo_pago`
reseteaba la fecha base a HOY cuando estaba vencida y siempre avanzaba
+1 mes fijo — un cliente atrasado 2 meses que pagaba 1 quedaba "al día"
artificialmente, sin dejar registrado el mes que aún debía. El fix:
- `calcular_n_meses(monto, precio_mes)`: cuántos meses cubre un pago.
- `Pago.n_meses`: nuevo campo, calculado al crear el `Pago`.
- `_avanzar_fecha_proximo_pago(pago)`: cambia de firma
  `(suscripcion)`→`(pago)`, avanza SIEMPRE desde la fecha anterior (nunca
  resetea a hoy) y por `pago.n_meses` periodos.
- `Suscripcion.meses_atraso`: meses completos de atraso (NUEVO).
- Selector "cuántos meses querés pagar" en el checkout + grilla "Estado por
  mes" (`grid_meses`, ventana de 6 meses).

Confirmado en código real de SD (`git show origin/main:pagos/views.py`,
líneas 23-41): mismo bug, sin `n_meses`/`meses_atraso` todavía. El fix es
**aplicar sobre lo ya existente**, no un port desde cero.

### ⚠️ Hallazgo crítico #1 (corrige a F1) — `Suscripcion.alerta_pago_vencido` YA EXISTE en SD

F1 reportó (grep contra el checkout LOCAL, desactualizado) que SD "no tiene
`alerta_pago_vencido` todavía" y que había que portarla completa. **Es
incorrecto.** El repo local (`~/Desktop/Repos/SD`) está **5 commits detrás**
de `origin/main` (confirmado: `git status` → "behind by 5 commits,
fast-forwardable"; `git log HEAD..origin/main --oneline`):

```
d22086c Merge pull request #91 from Indunnova16/feat/sd-banner-5dias
ab0eecb test(pagos): cobertura alerta_pago_vencido + banner global
2daeebd feat(pagos): banner global de aviso de pago 5+ dias vencido
c94550f feat(pagos): context processor global para alerta_pago_vencido
aa0229b feat(pagos): property alerta_pago_vencido (5 dias de gracia)
```

Es decir: **SD ya tiene `alerta_pago_vencido`** (issue #91, mergeado a
`main`, aún no pulled localmente), con banner global en el navbar
(`pagos/context_processors.py:alertas_pago` + bloque en
`templates/partials/navbar.html`) + 5 tests dedicados
(`pagos/tests/test_alerta_pago_vencido.py`, 273 líneas). Coincide
exactamente con lo que dice el propio mensaje del commit fuente
`f05a303` en `pagos-template`: *"Suscripcion.alerta_pago_vencido: backport
desde los 5 repos que ya lo tenían (banner a los 5 días de vencido) — el
template canónico no lo tenía, quedaba desincronizado."* — **SD es uno de
esos 5 repos.** El template la agregó copiándola DE repos como SD, no al
revés.

Diff de semántica (no bloqueante, ambas formas son equivalentes en la
práctica): la versión de SD chequea `self.requiere_pago` antes del gate de
5 días; la del template solo chequea `fecha_proximo_pago`. Como
`requiere_pago` ya es `True` en cualquier escenario donde el gap de 5+ días
aplica (excepto el edge case teórico `estado=ACTIVA` con
`fecha_proximo_pago` nulo, que ya retorna `False` en ambas), el
comportamiento observable es idéntico. **Acción: sub-item A3 abajo es
"verificar y reconciliar", NO "portar desde cero".**

### ⚠️ Hallazgo crítico #2 — repo local desincronizado, F3 debe sincronizar ANTES de editar

Mismo gotcha que golpeó a `PlasticosAmbientales#111` en este mismo RUN
(ver evento F1 de ese issue). Si F3 edita sobre el checkout local (HEAD
`c79401d`) sin sincronizar primero, **pisaría/perdería silenciosamente**
`alerta_pago_vencido`, el context processor y el banner del navbar (#91) —
o generaría un merge conflict feo al hacer `git pull` después de haber
commiteado sobre una base vieja. **F3 debe correr `git pull` (fast-forward,
sin conflictos posibles: local no tiene commits propios divergentes) antes
de tocar `pagos/models.py`/`config/settings/base.py`/
`templates/partials/navbar.html`.**

### ⚠️ Hallazgo crítico #3 — no hay atraso real en prod hoy para validar el fix en vivo

Miguel pidió confirmar cuántas suscripciones activas tienen atraso real
antes de que F3 codee. SELECT contra BD prod (`sd_lms`, proxy
`127.0.0.1:5434`, solo lectura):

```sql
SELECT id, estado, fecha_proximo_pago,
       CURRENT_DATE - fecha_proximo_pago AS dias_vencido
FROM pagos_suscripcion;
-- id=15 | PENDIENTE | 2026-08-01 | -2 dias (AÚN NO VENCE)

SELECT count(*) FROM pagos_pago;  -- 0 (cero pagos históricos)

SELECT datos_facturacion_id FROM pagos_suscripcion WHERE id=15;  -- NULL
```

**Resultado: 0 suscripciones con atraso real hoy.** SD (single-tenant,
`Suscripcion.objects.first()`) tiene exactamente 1 fila (`id=15`,
`fecha_proximo_pago=2026-08-01`, 2 días en el futuro respecto a hoy
2026-07-30) — `meses_atraso` calcularía `0`. Además `datos_facturacion_id`
es `NULL`, lo que en `portal.html` gatea TODO el bloque del selector/widget/
grilla detrás de `{% if datos_facturacion %}` (la rama que se renderiza hoy
es el CTA "Completar Datos de Facturación").

**Consecuencia arquitectónica para el smoke E2E (Sprint C / journey
`SD_92.yaml`):** al ser single-tenant con `.first()` (ordena por PK
ascendente sin filtro), **no es posible fabricar un fixture de
`Suscripcion` con atraso vía `psql_exec` para que el portal lo use** — el
fixture nuevo siempre tendría un `id` mayor al `15` ya existente, así que
`.first()` seguiría devolviendo la fila real (a diferencia de cuando F5 de
#85 corrió el mismo patrón: en ese momento la tabla estaba vacía, así que
el fixture SÍ era la única/primera fila). Mutar la fila real `id=15` está
fuera de cuestión: es la relación de facturación real Indunnova↔SD, no un
fixture — ninguna fase de este RUN escribe ahí sin HITL explícito.

**Decisión (aplica el gate de disponibilidad de dato-estado, Kaizen #53):**
`count=0` → la validación de "atraso > 0" / selector multi-mes / grilla
"Estado por mes" queda **`data_seed_absent` + 🟡**, cubierta EXCLUSIVAMENTE
por unit tests con fixtures aisladas de Django TestCase (A9/A10 — DB de test
limpia, sin el conflicto de `.first()` con datos reales). El journey E2E
(`SD_92.yaml`) queda acotado a un **read-only de regresión** contra el
estado real de prod: confirma que el código nuevo no rompe el render actual
(sin `datos_facturacion`) — ver sección Validación esperada.

## Sub-items (Sprint A — deployable como conjunto único, sin bloqueos)

| # | Sub-item | Archivos | Tests | Dependencias | Complexity | Estado |
|---|---|---|---|---|---|---|
| A0 | Sincronizar repo local a `origin/main` (`git pull`, fast-forward limpio) — trae #91 (`alerta_pago_vencido`+banner+context processor) que el checkout local no tiene | — (operativo, ningún archivo de código) | - | - | trivial | ⏳ pendiente |
| A1 | `calcular_n_meses(monto, precio_mes)` helper + `Pago.n_meses` (`PositiveSmallIntegerField`, `default=1`) + migración `0002_pago_n_meses.py` | `pagos/models.py`, `pagos/migrations/0002_pago_n_meses.py` | `CalcularNMesesTests` (5 casos) | A0 | low | ⏳ pendiente |
| A2 | `Suscripcion.meses_atraso` property (NUEVA — meses completos de atraso, 0 si al día) | `pagos/models.py` | `MesesAtrasoPropertyTests` (4 casos) | A0 | trivial | ⏳ pendiente |
| A3 | **Reconciliar** `Suscripcion.alerta_pago_vencido` — YA EXISTE (issue #91/`origin/main`). Confirmar que sigue intacta tras A0 y que es compatible con `meses_atraso` (ambas properties, sin overlap de campos). **NO reimplementar.** | `pagos/models.py` (verificación, 0 líneas nuevas esperadas) | ya cubierta por `test_alerta_pago_vencido.py` (5 tests, #91) — solo confirmar que siguen en verde | A0 | trivial | ⏳ pendiente |
| A4 | `_avanzar_fecha_proximo_pago(pago)`: cambia firma `(suscripcion)`→`(pago)`, agrega helper `_sumar_meses(fecha, n_meses)`, avanza SIEMPRE desde `fecha_proximo_pago` anterior (nunca resetea a hoy) y por `pago.n_meses` periodos | `pagos/views.py` | ver A9 (`AvanzarFechaProximoPagoHelperTests` actualizado + 2 casos nuevos) | A1 | medium | ⏳ pendiente |
| A5 | Ambos call sites (`PagoPortalView._procesar_transaccion_wompi` [redirect] y `WompiWebhookView.post` [webhook]) calculan `n_meses = calcular_n_meses(amount, suscripcion.plan.precio)` al crear el `Pago`, y pasan a llamar `_avanzar_fecha_proximo_pago(pago)` en vez de `(suscripcion)` | `pagos/views.py` | ver A10 (`WebhookNMesesTests`) | A1, A4 | low | ⏳ pendiente |
| A6 | `PagoPortalView.get_context_data`: agrega `meses_atraso`, `opciones_pago`/`opciones_pago_json` (N=1..max(6,atraso+1), referencia+firma por opción), `meses_sugeridos`, `grid_meses` (helper `_grid_meses`, ventana 6 meses, pagado/pendiente derivado de `fecha_proximo_pago` como cursor) | `pagos/views.py` | ver A10 (`CheckoutOpcionesPagoTests`, `GridMesesTests`) | A1, A2 | medium | ⏳ pendiente |
| A7 | `alegra.py` `crear_factura`: reusa `pago.n_meses` (ya calculado en A5) en vez de recalcular `meses = max(1, round(monto/precio_mes))` inline (hoy duplicado) | `pagos/alegra.py` | `AlegraMontoRegressionTests` ya existente debe seguir en verde (confirma que sigue facturando por `pago.monto`) | A1 | low | ⏳ pendiente |
| A8 | `templates/pagos/portal.html`: banner `{% if meses_atraso > 0 %}` ("Debés N meses de suscripción..."), selector `<select id="pago-meses-select">` pre-llenado con `meses_sugeridos`, JS que intercambia atributos del `<script>` widget WOMPI sin reload al cambiar de opción, grilla "Estado por mes" (`grid_meses`, badges verde/rojo) | `templates/pagos/portal.html` | ver journey `SD_92.yaml` (read-only, marcado `# RECONCILIAR_DOM`) + code review contra diff verbatim del template | A6 | medium | ⏳ pendiente |
| A9 | Adaptar `pagos/tests/test_issue_2.py`: `AvanzarFechaProximoPagoHelperTests` (3 tests existentes cambian de `_avanzar_fecha_proximo_pago(s)` a `_avanzar_fecha_proximo_pago(self._pago(s, n_meses=N))` + helper `_pago()` + 2 tests nuevos de regresión del bug — "vencida 2 meses, paga 1, sigue debiendo" y "paga 2, avanza 2 periodos"); portar `CalcularNMesesTests` (5 casos) y `MesesAtrasoPropertyTests` (4 casos) tal cual (no dependen de usuarios). **NO portar `AlertaPagoVencidoTests` del template — redundante con `test_alerta_pago_vencido.py` ya existente en SD (#91).** | `pagos/tests/test_issue_2.py` | 12 tests existentes se mantienen en verde + 11 nuevos (2+5+4) | A1, A2, A4 | medium | ⏳ pendiente |
| A10 | Portar `pagos/tests/test_pago_multiple_meses.py` completo (`CheckoutOpcionesPagoTests`, `WebhookNMesesTests`, `GridMesesTests` — 3 clases, ~10 tests) adaptando los 3 sitios que usan `_crear_usuario_test(username=...)` (helper que el template importa pero SD NO tiene) a `_crear_administrador(document_number=..., password=...)` (helper real de SD en `test_issue_2.py`, ya asigna `rol=ADMINISTRADOR` — necesario porque `PagoPortalView` está gateada RBAC desde #85/A3) — usar `document_number` distintos por test para no chocar con el `unique` implícito del PK de usuario | `pagos/tests/test_pago_multiple_meses.py` (nuevo) | ~10 tests nuevos, DB de test aislada (sin el conflicto `.first()` de prod — ver Hallazgo #3) | A1, A2, A4, A5, A6 | medium | ⏳ pendiente |

**Deployable_solo: true** — a diferencia de #85 (que tenía Sprint B
bloqueado por secrets/precio real), este fix no requiere ningún insumo de
negocio nuevo: los secrets WOMPI/Alegra y el `PlanServicio` YA existen en
prod (confirmado: `Suscripcion.plan_id` resuelve a un plan real,
`"S.D. S.A.S. — Sostenimiento LMS"`, \$150.000 COP). Sprint A completo es
la versión 1.0 a entregar.

## DAG dependencias

```
A0 → A1, A2, A3 (sincronizar ANTES de tocar pagos/models.py)
A1 → A4, A5, A6, A7, A9, A10
A2 → A6, A9, A10
A3 → (independiente, solo verificación)
A4 → A5, A9, A10
A5 → A10
A6 → A8, A10
A7 → (independiente una vez A1)
A8 → (UI, depende de A6)
```

## Riesgos y mitigaciones

- **Repo local desincronizado (Hallazgo #2).** Mitigado con A0 como
  PRIMER paso bloqueante — `git pull` fast-forward, sin commits locales
  propios que puedan generar conflicto.
- **F1 dio un falso negativo sobre `alerta_pago_vencido` (Hallazgo #1).**
  Mitigado explícitamente: A3 es "verificar", no "portar". Si F3 la
  reimplementa desde cero sin haber sincronizado (A0), pisaría la versión
  de #91 con una funcionalmente equivalente pero textualmente distinta —
  bajo riesgo real, pero trabajo duplicado y un diff más grande de lo
  necesario para revisar.
- **Sitio disperso real: 2 call sites deben calcular `n_meses` de forma
  idéntica** (A5 — redirect y webhook). No dispara el gate mecánico de
  `sitios_checklist` (ningún sub-item es `epic`, `riesgo_global` es
  `medio` no `alto`), pero es el mismo patrón de fondo que ese gate ataca:
  si solo uno de los 2 call sites calcula `n_meses`, el otro dejaría
  `Pago.n_meses` en su `default=1` silenciosamente — mismo bug de origen,
  versión 2. Verificación manual explícita en el smoke de F5: grep de
  `calcular_n_meses(` en `pagos/views.py` debe dar exactamente 2 matches.
- **Gate de disponibilidad de dato-estado (Hallazgo #3).** 0 suscripciones
  con atraso real en prod hoy + `datos_facturacion_id IS NULL` en la única
  fila existente + arquitectura single-tenant `.first()` que impide
  fixturear un fallback. La validación del selector/grilla/banner de atraso
  queda **exclusivamente en unit tests** (A9/A10) — el journey E2E NO
  puede reclamar 🟢 sobre esos elementos, solo sobre el render-only de
  regresión contra el estado real actual. **No es un gap de este plan: es
  una limitación estructural del dato real hoy**, documentada para que F5
  no intente forzar un mutativo imposible ni sobre-declare validación.
- **Alegra es cuenta compartida de producción, sin sandbox distinguible**
  (mismo riesgo ya documentado en el plan de #85) — A7 no dispara
  facturación real, solo cambia de dónde lee `n_meses`; cubierto por
  `AlegraMontoRegressionTests` (mock).
- **Riesgo global: medio** (F1) — ratificado: cambios acotados a un módulo
  ya probado en prod, diff fuente verificado línea por línea contra
  `pagos-template@f05a303`, sin dependencias externas nuevas ni cambios de
  esquema destructivos (migración aditiva, campo con `default=1`).
- **Falso positivo esperable en el gate `--require-pdf` de `lint_journey.py`
  (F5/closeout).** `derive_require_pdf()` dispara `require_pdf=True` de forma
  **incondicional** apenas `--changed-files` incluye una migración
  (`pagos/migrations/0002_pago_n_meses.py` — confirmado leyendo el código del
  script, línea `if migration_files: return True, ...`, ANTES de llegar a la
  exención `--repo-root` que sí aplicaría si solo `models.py` estuviera en la
  lista). `pagos/` no tiene ningún consumidor de PDF/export
  (`grep -rliE "weasyprint|reportlab|openpyxl|xlsxwriter|csv\.writer" pagos/`
  → 0 matches, confirmado). Si F5 corre `lint_journey.py --changed-files ...
  --require-pdf` (heredado) y bloquea pidiendo un journey PDF que no existe
  ni tiene sentido para este módulo, es un falso positivo conocido — no
  hackear un journey PDF inventado; documentar la evidencia del grep como
  justificación y escalar si el gate no tiene otra salida.

## Validación esperada (DoD)

- [x] Migration: A1 (`0002_pago_n_meses.py`, aditiva, `default=1` — no
  requiere backfill).
- [x] Backend endpoint + form + lógica: A1, A2, A3 (verificación), A4, A5,
  A6, A7.
- [x] UI con estados completos: A8 (banner atraso, selector, grilla,
  mensaje de éxito ya existente sin cambios).
- [x] Tests cubren happy + ≥2 edge cases: A9 (11 nuevos, incl. los 2 casos
  de regresión del bug original) + A10 (~10 nuevos).
- [x] Smoke E2E definido: journey `SD_92.yaml` — read-only de regresión
  contra prod real (ver Hallazgo #3 para por qué no es mutativo).
- [x] Instrucciones de validación cliente: ver abajo.

### Instrucciones de validación para Miguel/cliente (post-deploy)

1. `/pagos/` como administrador → confirmar que la página sigue
   respondiendo 200 y mostrando el CTA de "Completar Datos de Facturación"
   (estado actual real, sin cambios visibles todavía porque
   `datos_facturacion` sigue vacío).
2. Para ver el selector de meses y la grilla en acción, se necesita
   completar el formulario de Datos de Facturación de SD real (`/pagos/
   facturacion/`) — **esto es una tarea de negocio pendiente, no parte de
   #92** (la Suscripción real de SD nunca tuvo datos de facturación
   cargados). Una vez cargados, el selector/grilla se activan
   automáticamente sin deploy adicional.
3. Verificación funcional real del fix (sin esperar a que se cumpla el
   punto 2): correr `python manage.py test pagos` en CI/local — los ~21
   tests nuevos (A9+A10) ejercitan el escenario completo "cliente atrasado
   2 meses paga 1 → sigue debiendo 1, no queda al día artificialmente" con
   fixtures aisladas.
