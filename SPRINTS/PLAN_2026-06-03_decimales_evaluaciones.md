# PLAN — Puntuación decimal en evaluaciones/quizes (issue #39)

**Fecha:** 2026-06-03
**Issue:** [Indunnova16/SD#39](https://github.com/Indunnova16/SD/issues/39)
**Estado:** Planning completado, listo para ejecución
**Ruta:** sprint_path (versión 1.0 completa, NO MVP)

## Contexto

Hoy `Question.points` y `Assessment.passing_score` son `PositiveIntegerField`,
mientras que `AssessmentAttempt.score` y `AttemptAnswer.points_awarded` YA son
`DecimalField(max_digits=5, decimal_places=2)`. Esa inconsistencia impide
calificaciones como 4.5 / 3.8 que el cliente Salomón Durán pidió (reunión
2026-05-27). La versión 1.0 completa convierte el flujo de entrada de puntos a
`Decimal` punta a punta: modelos, migración, formularios, parsing en vistas,
servicio de scoring, templates con formato es-CO correcto, y tests con datos
legacy + edge cases decimales.

### Evidencia de código (literal, inspeccionado)

- `apps/assessments/models.py:64` → `passing_score = models.PositiveIntegerField(...)`
- `apps/assessments/models.py:163` → `points = models.PositiveIntegerField(_("Puntos"), default=1)`
- `apps/assessments/models.py:255` → `points_earned = models.PositiveIntegerField(default=0)` (trunca decimales del scoring)
- `apps/assessments/models.py:124-128` → `total_points` usa `Sum("points")` (queda Decimal automáticamente al cambiar el campo)
- `apps/assessments/services.py:250` → `attempt_answer.points_awarded = question.points` (ya Decimal-compatible)
- `apps/assessments/services.py:310` → `attempt.points_earned = int(points_earned)` (TRUNCA — bug a corregir)
- `apps/assessments/services.py:553,564,570,597,635` → aritmética de puntos con int (revisar)
- `apps/courses/forms.py:444` → `passing_score = forms.IntegerField(...)` (QuickAssessmentForm)
- `apps/courses/forms.py:470-535` → `AssessmentEditForm` (ModelForm) + `clean_passing_score` (acepta solo int por el field del modelo)
- `apps/courses/views.py:1649,1726` → `points = int(request.POST.get("points", 1))` (parse de Question.points en add/edit)
- `apps/courses/views.py:1192` → `points=int(qdata.get("points", 1))` (inline builder JSON)
- `apps/core/validators.py:24-36` → `validate_percentage` ya soporta decimales (solo compara rango 0-100); NO requiere cambio funcional
- Templates: `take_assessment.html:50`, `attempt_result.html:29,88`, `assessment_detail.html:38,42`, `assessment_list.html:44`, `question_item.html:27` muestran puntos; `question_form.html:13,78` inyecta `{{ question.points }}` en Alpine `x-data` + input number (RIESGO locale es-CO)

### Gotchas es-CO aplicables (memorias)

- **`{{ question.points }}` dentro de `x-data` (question_form.html:13):** si points fuera float localizado (`4,5`) rompería el bundle Alpine con `Unexpected token`. Mitigación: usar `{{ question.points|stringformat:"g" }}` o `{% localize off %}{{ question.points }}{% endlocalize %}` para que salga con punto decimal.
- **`<input type="number" value="{{ x|floatformat:2 }}">`:** floatformat produce coma (`75,50`) y el navegador deja el campo VACÍO. Para inputs decimales usar sufijo `u`: `floatformat:'-2u'` (NO `localize off` que no corrige floatformat).
- **floatformat con sufijo `u`** para todo display de puntos/score en templates de resultados.

## Sub-items (Sprint A — único sprint, deployable en bloque)

### Sprint A (deployable_solo: true — todo va en un solo PR/deploy atómico)

| # | Sub-item | Archivos | Tests | Dependencias | Estado |
|---|---|---|---|---|---|
| A1 | Modelos: `Question.points`, `Assessment.passing_score` y `AssessmentAttempt.points_earned` → `DecimalField(max_digits=5, decimal_places=2)`. `points` default `Decimal("1.00")`, `passing_score` default `Decimal("80.00")`, `points_earned` default `Decimal("0.00")`. Mantener `validate_percentage` en passing_score. | `apps/assessments/models.py` | (cubierto por A8) | - | ⏳ pendiente |
| A2 | Migración `makemigrations assessments` → `0004_decimal_points.py` con 3 `AlterField`. Verificar hermético con `makemigrations --check`. Datos legacy enteros migran sin pérdida (int→decimal es seguro). | `apps/assessments/migrations/0004_decimal_points.py` (nueva) | smoke migrate | A1 | ⏳ pendiente |
| A3 | Formularios: `QuickAssessmentForm.passing_score` y campo `passing_score` de `AssessmentEditForm` → `forms.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100)`. Widget `NumberInput` con `step="0.01"`. Ajustar `clean_passing_score` (Decimal vs 0-100). | `apps/courses/forms.py` | A8 | A1 | ⏳ pendiente |
| A4 | Parsing en vistas: `builder_add_question` (1649), `builder_edit_question` (1726) e inline builder (1192) → `Decimal(str(request.POST.get("points", "1")))` con `try/except InvalidOperation` → 400 "Puntos inválido". | `apps/courses/views.py` | A8 | A1 | ⏳ pendiente |
| A5 | Servicio scoring: `services.py:310` quitar `int(...)` → `attempt.points_earned = points_earned` (Decimal). Revisar `auto_grade_attempt` (553/564/570/597) y `calculate_score` (635): forzar Decimal en `points_awarded`, `total_points`, `earned_points`; división con `Decimal` y `quantize` del score a 2 decimales para evitar `5.00 / 3 = 1.6666...`. `grade_essay_answer` ya recibe Decimal. | `apps/assessments/services.py` | A8 | A1 | ⏳ pendiente |
| A6 | Templates resultados: formatear puntos con `floatformat:'-2u'` donde se muestra `question.points` / `points_earned` / `total_points` / `passing_score` (`take_assessment.html:50`, `attempt_result.html:29,88`, `assessment_detail.html:38,42`, `assessment_list.html:44`, `question_item.html:27`). Mantener `pluralize` coherente. | `templates/assessments/take_assessment.html`, `templates/assessments/attempt_result.html`, `templates/assessments/assessment_detail.html`, `templates/assessments/assessment_list.html`, `templates/courses/partials/builder/question_item.html` | A8 (E2E) | A1 | ⏳ pendiente |
| A7 | Builder UI (Alpine): `question_form.html:13` `{{ question.points }}` → `{% localize off %}{{ question.points }}{% endlocalize %}` (evitar coma en x-data); input number (78) agregar `step="0.01"`. Quiz inline + properties form: inputs passing_score `step="0.01"`. Si form re-renderiza valor decimal en input, usar `floatformat:'-2u'`. | `templates/courses/partials/builder/question_form.html`, `templates/courses/partials/builder/quiz_inline_form.html`, `templates/courses/partials/builder/assessment_properties_form.html` | A10 (E2E) | A1 | ⏳ pendiente |
| A8 | Tests servicio: scoring con puntos decimales (4.5, 3.8), score con `quantize` 2 decimales, edge cases (0.5, 99.99, total_points=0), `grade_essay_answer` con Decimal, `auto_grade_attempt`/`calculate_score` con mix. Test contra ≥1 assessment legacy (passing_score entero migrado). | `apps/assessments/tests/test_services.py` | — | A1,A2,A5 | ⏳ pendiente |
| A9 | Tests API/forms: `QuickAssessmentForm`/`AssessmentEditForm` aceptan 75.5 y rechazan 100.5; endpoint add/edit question persiste points=2.5; `validate_percentage` con 75.5 OK / 100.01 falla. | `apps/assessments/tests/test_api.py` | — | A1,A3,A4 | ⏳ pendiente |
| A10 | Smoke E2E (journey SD_39.yaml): editar assessment legacy id=10 poniendo passing_score=75.5 vía builder edit endpoint, verificar persistencia `passing_score=75.50` via psql_select, restaurar a 80. + render read-only de detalle muestra decimal. | `RUN_DIR/journeys/SD_39.yaml` | — | A2,A3,A6 | ⏳ pendiente |

## DAG dependencias

```
A1 → A2, A3, A4, A5, A6, A7
A5 → A8 (requiere A1, A2)
A3 → A9 (requiere A1)
A4 → A9 (requiere A1)
A2,A3,A6 → A10 (E2E final, requiere deploy)
```

`primer_sub_conjunto_deployable`: todos (A1..A10) van juntos. El cambio NO es
fragmentable de forma segura porque la migración (A2) y el form (A3) deben ir
junto al modelo (A1) o el form valida contra un field aún entero. Deploy atómico.

## Riesgos y mitigaciones

- **es-CO coma decimal en Alpine x-data (question_form.html):** `{% localize off %}` en A7. RIESGO alto si se omite → rompe el builder completo. Sin localize off, `points=4,5` → `Unexpected token ','` aborta el bundle.
- **input type=number con floatformat coma:** usar sufijo `u` (`-2u`) en A6/A7, NO `localize off` solo. Sin esto el campo se ve vacío.
- **División Decimal no exacta** (`5/3*100`): `quantize(Decimal("0.01"))` en A5 para evitar `score` con 28 decimales que excede `max_digits=5`.
- **`points_earned` truncado a int (services.py:310 + modelo):** A1+A5 lo corrigen; sin A1 el modelo sigue truncando aunque el cálculo sea Decimal.
- **Migración sobre datos legacy:** int→Decimal es widening seguro; no requiere data migration. Validar con assessment legacy id=10 (passing_score=80 → 80.00).
- **Conflicto de número de migración** (último es 0003): pre-asignar `0004_decimal_points`. Verificar `makemigrations --check` hermético antes de F4.

## Validación esperada (qa_claude smoke + E2E)

- Login `qa_claude@indunnova.com` (id=7, campo form `username`, autentica por email). Verificar `is_active=true` antes (gotcha 2026-06-03).
- E2E SD_39.yaml: editar assessment legacy id=10 (course 63) → passing_score 75.5 → persiste 75.50 en BD → restaurar 80.
- Smoke maestros: builder de curso 63 (lista assessments + editar properties + agregar pregunta con points=2.5), detalle de assessment renderiza `75,5%` / puntos con decimal, take_assessment muestra puntos decimales. HTTP 200 en todo.
- Service Cloud Run `sd-lms` (https://sd-lms-rvfp6uj2va-uc.a.run.app), BD `sd_lms`.

## Instrucciones de validación cliente (para comentario F6)

1. Entrar al constructor de un curso → editar una evaluación → poner Puntaje mínimo `75.5` → Guardar. Debe aceptarlo y mostrar `75,5%`.
2. Agregar/editar una pregunta con Puntos `2.5`. Debe guardarse y mostrarse con decimales.
3. Resolver el quiz → la calificación obtenida refleja puntos decimales (ej. 7,5/10).
