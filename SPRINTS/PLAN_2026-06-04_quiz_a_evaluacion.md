# PLAN — Terminología "Quiz" → "Evaluación" en UI (issue #35)

**Fecha:** 2026-06-04
**Issue:** [Indunnova16/SD#35](https://github.com/Indunnova16/SD/issues/35)
**Estado:** Planning completado, listo para ejecución
**Ruta:** sprint_path (cambio amplio: 3 archivos Python + ~8 templates)

## Contexto
Cambiar la terminología visible al usuario de "Quiz" a "Evaluación" en TODO el
aplicativo LMS, SIN renombrar modelos, clases, valores internos, URLs ni
nombres de funciones/JS/CSS. Solo cambian strings de cara al usuario:
`verbose_name`/labels de choices/help_text/textos en templates. El valor
interno `lesson_type='quiz'` / `assessment_type='quiz'` se mantiene; las
rutas `builder_assign_quiz`, `builder_create_quiz`, etc. se mantienen.

**SIN migración** — cambiar el segundo elemento (label) de un `TextChoices`
no genera migración de esquema (solo cambia `choices`, que Django no migra si
el valor no cambia; aun si makemigrations detecta `choices`, NO altera datos).
Confirmar con `makemigrations --check --dry-run`; si genera una de solo
`AlterField(choices=...)` es inocua y puede aplicarse, pero el plan asume cero
cambio de datos.

## Coordinación BUNDLE con SD#36 (CRÍTICO)
Este RUN ejecuta **#36 ANTES que #35** en el mismo worktree. #36 elimina el
botón "Asignar Quiz" de `lesson_item.html` (líneas ~105-110, el `<button>`
con `title="Asignar Quiz"` y `@click="showQuizAssign..."`).

⚠️ Cuando #35 corra, **ese botón ya no existirá**. El sub-item que toca
`lesson_item.html` (S4) debe:
- NO intentar renombrar el texto "Asignar Quiz" del botón (ya eliminado por #36).
- Renombrar SOLO lo que quede: badge "Sin quiz asignado" (L81), `<option>Quiz`
  (L191), y verificar que el panel `quiz_selector` incluido (L304) siga siendo
  alcanzable por otra vía si #36 cambió el trigger.
- F3 debe re-grepear `lesson_item.html` en vivo (post-#36) antes de editar,
  NO confiar en los números de línea de este plan para ese archivo.

## Inventario de strings VISIBLES a cambiar (verificado por F1+F2, 2026-06-04)

### Python (labels de cara al usuario)
| Archivo | Línea | Actual | Nuevo |
|---|---|---|---|
| apps/assessments/models.py | 32 | `QUIZ = "quiz", _("Quiz")` | label → `_("Evaluación")` (valor "quiz" intacto) |
| apps/courses/models.py | 350 | `QUIZ = "quiz", _("Quiz")` | label → `_("Evaluación")` (valor intacto) |
| apps/courses/forms.py | 477 | `("quiz", _("Quiz"))` | `("quiz", _("Evaluación"))` |

> El docstring `Assessment/Quiz model.` (models.py:28) es comentario interno → NO cambiar.

### Templates (texto visible literal)
| Archivo | Línea(s) | Actual | Nuevo |
|---|---|---|---|
| templates/courses/lesson_view.html | 212 | `📋 Quiz: {{ lesson.title }}` | `📋 Evaluación: {{ lesson.title }}` |
| templates/courses/lesson_view.html | 241 | `...para aprobar este quiz.` | `...para aprobar esta evaluación.` |
| templates/courses/lesson_view.html | 252 | `Comenzar Quiz` | `Comenzar Evaluación` |
| templates/courses/lesson_view.html | 256 | `...Este quiz está en borrador...iniciarlo.` | `...Esta evaluación está en borrador...iniciarla.` |
| templates/courses/lesson_view.html | 261 | `Este quiz aún no ha sido configurado...` | `Esta evaluación aún no ha sido configurada...` |
| templates/courses/course_detail.html | 138 | `<span class="sr-only">Quiz:</span>` | `<span class="sr-only">Evaluación:</span>` |
| templates/courses/partials/builder/lesson_form.html | 47 | `<option value="quiz">Quiz</option>` | label → `Evaluación` (value intacto) |
| templates/courses/partials/builder/lesson_form.html | 241 | `>Crear Quiz<` | `>Crear Evaluación<` |
| templates/courses/partials/builder/lesson_item.html | 81 | `Sin quiz asignado` | `Sin evaluación asignada` |
| templates/courses/partials/builder/lesson_item.html | 191 | `<option value="quiz">Quiz</option>` | label → `Evaluación` |
| templates/courses/partials/builder/quiz_inline_form.html | 28 | `<option value="quiz">Quiz</option>` | label → `Evaluación` |
| templates/assessments/assessment_list.html | 24 | badge `get_assessment_type_display` | (se actualiza solo al cambiar models.py:32) — verificar |
| templates/assessments/assessment_detail.html | 6 | badge `get_assessment_type_display` | (se actualiza solo) — verificar |

> NO TOCAR (internos): `value="quiz"`, `data-show-for="quiz"`, `id="quizBuilder"`,
> `name="quiz_questions"`, vars JS `QuizBuilder`/`quizBuilder`/`showQuizAssign`/
> `showCreateQuiz`/`showQuizSelector`, clases CSS `.quiz-form`/`.quiz-list`,
> `{% url 'courses:builder_*_quiz' %}`, comentarios HTML `<!-- ... -->`,
> condicionales `lesson.lesson_type == 'quiz'` / `assessment_type == 'quiz'`.
> El comentario `Quiz selector partial...` (quiz_selector.html:2) es interno → opcional.

> NOTA: quiz_selector.html ya dice "Asignar Evaluacion" / "Crear nueva
> evaluacion" (sin tilde). F3 puede normalizar tildes (Evaluación) pero NO es
> bloqueante. assessment_list/detail ya tienen título "Evaluaciones".

## Sub-items por sprint

### Sprint A (deployable_solo: false — es un bundle atómico de terminología)
| # | Sub-item | Archivos | Tests | Dependencias | Estado |
|---|---|---|---|---|---|
| A1 | Cambiar labels en models (assessments + courses) | apps/assessments/models.py:32, apps/courses/models.py:350 | makemigrations --check (cero migración nueva esperada) | - | ⏳ |
| A2 | Cambiar choice label en form | apps/courses/forms.py:477 | render form en builder | A1 | ⏳ |
| A3 | Renombrar texto visible en lesson_view + course_detail | templates/courses/lesson_view.html (212,241,252,256,261), course_detail.html (138) | grep -c "Quiz" debe bajar; render lesson_view | - | ⏳ |
| A4 | Renombrar texto visible builder (post-#36) | lesson_form.html (47,241), lesson_item.html (81,191), quiz_inline_form.html (28) | RE-grep lesson_item EN VIVO antes de editar | #36 deploy/merge | ⏳ |
| A5 | Verificar badges auto-actualizados | assessment_list.html (24), assessment_detail.html (6) | smoke /assessments/ + /assessments/10/ | A1 | ⏳ |

## DAG dependencias
A1 → A2, A5
#36 → A4 (A4 espera a que #36 elimine el botón "Asignar Quiz")
A3 independiente
A1, A2, A3, A4, A5 se deployan juntos (un solo deploy bundle al final del RUN)

## Riesgos y mitigaciones
- **R1 (alto): números de línea de lesson_item.html cambian tras #36.** Mitig:
  F3 debe `grep -ni "quiz" lesson_item.html` en vivo antes de editar, usar
  contexto textual, no líneas fijas.
- **R2 (medio): romper Alpine/JS al renombrar de más.** Mitig: allowlist
  estricta de "solo texto visible"; NUNCA tocar `x-data`, `id=`, `name=`,
  `value=`, clases CSS, `{% url %}`. Ver `feedback_django_comentarios_multilinea`.
- **R3 (bajo): migración inesperada por AlterField(choices).** Mitig:
  `makemigrations --check`; si aparece, es inocua (no toca datos) — incluir o
  descartar según política del repo, pero NO bloquea.
- **R4 (bajo): tildes inconsistentes ("Evaluacion" sin tilde ya presente).**
  Mitig: usar "Evaluación" con tilde en todo lo nuevo; normalizar existentes
  best-effort.

## Validación esperada (journey E2E autenticado — qa_claude)
- Login `/accounts/login/` (username/password).
- `/assessments/10/` (detalle de una evaluación tipo quiz): el badge de tipo
  debe decir **"Evaluación"**, NO "Quiz". Página ya tiene "Iniciar Evaluación".
- `/assessments/` (lista): badges de tipo → "Evaluación".
- Course builder `/courses/admin-courses/<id>/builder/`: el `<select>` de tipo
  de lección ofrece "Evaluación" (no "Quiz"); badge de lección quiz vía
  `get_lesson_type_display` → "Evaluación".
- assert NEGATIVO: en el bloque de tipo/badge visible NO debe aparecer "Quiz".
  (No se puede assert global no-"Quiz" en builder porque JS interno conserva
  "QuizBuilder"; el journey acota el assert al área de tipo de lección.)
