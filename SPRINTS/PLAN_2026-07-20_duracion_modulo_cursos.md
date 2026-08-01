# PLAN — Gestión de duración en módulo Cursos (issue #62)

**Fecha:** 2026-07-20
**Issue:** [Indunnova16/SD#62](https://github.com/Indunnova16/SD/issues/62)
**Estado:** Planning completado, listo para ejecución

## Contexto

Hallazgo interno de QA (Andrea Velásquez) sobre el módulo Cursos del LMS: 5
problemas relacionados con el campo `Lesson.duration` y su uso a lo largo del
aplicativo, verificados línea por línea contra el código antes de abrir el
issue. Versión 1.0 completa a entregar:

(a) **backend** — `Module.duration_hours` nuevo (análogo a `Course.duration_hours`
ya existente), `duration` obligatorio en `LessonBuilderForm` con manejo de
lecciones ya guardadas con `duration=0`;
(b) **UI Constructor** — mostrar "Duración (minutos)" también para lecciones
tipo Evaluación (quiz), marcarlo requerido visualmente, contador de horas en
vivo (módulo + curso) sin recargar;
(c) **unificación** de duración en horas (`duration_hours`) en
`course_detail`, `course_list`, `path_detail` (hoy minutos crudos vía
`total_duration`), y AGREGAR duración —hoy ausente— en `certificate_detail` y
`my_certificates`;
(d) **decisión pendiente** (sub-item #1, NO bloqueante de los demás): mantener
el timer forzado de `externalVideoTracker` en lecciones de video externo o
implementar una alternativa;
(e) tests happy + edge cases; (f) smoke E2E autenticado; (g) comentario al
cliente con URLs de validación.

## Hallazgos de la inspección (evidencia para F3, no repetir el grep)

1. **`templates/courses/partials/builder/lesson_form.html:50-51`** — el div de
   Duración tiene `data-show-for="video,pdf,text,scorm,audio,interactive,presential"`
   y el `x-show` con la misma lista — falta `quiz`. Este es el formulario de
   **ALTA** de lección (`is_new=True`, incluido desde `module_card.html:131`).
2. **`templates/courses/partials/builder/lesson_item.html` (bloque de edición
   inline, ~línea 215-224)** — el input de Duración **NO tiene condicional
   `x-show`/`data-show-for` en absoluto**: ya se muestra para TODOS los tipos
   incluyendo quiz. Es decir, el bug de visibilidad de #62.2 existe SOLO en el
   formulario de alta, no en el de edición inline — asimetría real del código,
   no asunción.
3. **`apps/courses/forms.py:301-389` `LessonBuilderForm`** — `duration` no
   tiene `clean_duration()` ni override de `required`. Como
   `Lesson.duration` es `PositiveIntegerField(default=0, validators=[MinValueValidator(0)])`,
   el ModelForm ya lo trata como `required=True` a nivel de "campo presente",
   pero **`0` es un valor válido** que pasa esa validación — por eso hoy se
   puede guardar duration=0 silenciosamente. Se necesita un `clean_duration()`
   explícito que exija `> 0`.
4. **`apps/courses/models.py:305-341` `class Module`** — no tiene ninguna
   property de duración. `Course.duration_hours` (líneas 288-302) es el patrón
   a replicar: `round(Sum(lessons__duration)/60, 1)`.
5. **`templates/courses/partials/builder/module_card.html`** — hoy solo
   muestra `{{ module.lessons.count }} leccion(es)`, sin duración. El
   "contador en vivo" pedido debe agregarse aquí (encabezado del módulo) y en
   `templates/courses/course_builder.html` (`#course-info-card`, línea 22)
   para el total del curso.
6. **Mecanismo HTMX del builder**: `builder_add_lesson` / `builder_edit_lesson`
   / `builder_delete_lesson` (`apps/courses/views.py`) responden con **solo el
   fragmento de la lección tocada** (`lesson_item.html`), no con el
   `module_card.html` completo. Para que el contador de horas del módulo/curso
   se actualice "sin recargar" hace falta que esas 3 vistas agreguen un
   fragmento adicional con `hx-swap-oob="true"` apuntando al badge de horas
   del módulo (y, para consistencia, al del curso).
7. **`templates/courses/course_detail.html:22`** y
   **`templates/courses/course_list.html:115`** ya muestran
   `{{ course.total_duration }} min` — cambiar a `{{ course.duration_hours }}`
   (la property ya existe y ya es correcta, hoy sin usar en estos templates).
8. **`templates/learning_paths/path_detail.html:24`** muestra
   `{{ path.total_duration }} min`.
9. **🔴 HALLAZGO — bug preexistente en `apps/learning_paths/models.py:81-89`**:
   `LearningPath.total_duration` hace
   `self.path_courses.aggregate(total=Sum(F("course__total_duration"), ...))`,
   pero `Course.total_duration` es una **`@property` de Python**
   (`apps/courses/models.py:280-286`), NO un campo ni una annotation de BD. El
   ORM no puede resolver `F("course__total_duration")` contra una property —
   esto debería lanzar `django.core.exceptions.FieldError` en cuanto se
   evalúa `path.total_duration`, para CUALQUIER learning path. No hay tests
   que cubran esta property (`grep total_duration apps/learning_paths/`solo
   encuentra la definición y el serializer, cero tests) y no hay commits
   posteriores que la toquen. **Es directamente relevante para el sub-item
   (e) porque implica que `LearningPath.duration_hours` NO puede replicar esa
   lógica** — debe agregar directamente sobre
   `path_courses__course__modules__lessons__duration` (o iterar
   `course.duration_hours` en Python). Se corrige DENTRO de este issue porque
   es la misma property que el issue pide mostrar en `path_detail.html`, no
   scope creep.
10. **`templates/certifications/certificate_detail.html`** y
    **`templates/certifications/my_certificates.html`** — confirmado por
    grep: cero menciones de "duration" hoy. Hay que agregar una fila nueva en
    la sección "Datos del certificado" (certificate_detail, junto a
    Curso/Estado/Puntaje) y en el bloque "Details" de cada card
    (my_certificates), usando `certificate.course.duration_hours`.
11. **Dato real de riesgo (verificado en BD prod, `sd_lms`)**: de 25 lecciones
    existentes, **21 (84%) tienen `duration=0`**, incluidas 6 de las 7
    lecciones tipo quiz. Ver sección Riesgos.
12. **Sub-item #1 (decisión pendiente)** —
    `templates/courses/lesson_view.html:648-676`, Alpine
    `externalVideoTracker`: `totalDuration = lesson.duration * 60` es un timer
    de tiempo REAL transcurrido en la página (no detecta reproducción real del
    iframe cross-origin de YouTube/Vimeo) que debe agotarse antes de permitir
    "Marcar como completado". Es la única lección con esa restricción — PDF y
    Texto permiten completar de inmediato (línea ~457-476, sin condición de
    tiempo). Decisión de Miguel/equipo: mantener vs. alternativa (ej. % mínimo
    de reproducción). **NO bloquea los sub-items 2-5.**

## Sub-items por sprint

### Sprint A — versión 1.0 completa (deployable_solo: true, un solo PR/deploy)

| # | Sub-item | Archivos | Tests | Dependencias | Complexity | Estado |
|---|---|---|---|---|---|---|
| A0 | Decisión: timer forzado video externo (mantener vs. alternativa) | `templates/courses/lesson_view.html:648-676` | - | - | n/a (decisión) | ⏸ pendiente decisión Miguel/equipo — NO bloquea A1-A4 |
| A1 | Mostrar "Duración (minutos)" también para lecciones tipo Evaluación (quiz) en el form de ALTA | `templates/courses/partials/builder/lesson_form.html:50-51` (agregar `quiz` a `data-show-for` y al array del `x-show`) | Test de render: `data-show-for` incluye `quiz` con `is_new=True` | - | trivial | ⏳ pendiente |
| A2 | Hacer `duration` obligatorio (>0) en el Constructor para los tipos que lo muestran (video/pdf/text/scorm/audio/interactive/presential/quiz — excluye `attendance`, que usa `scheduled_date`), con manejo explícito de lecciones legacy en `duration=0` | `apps/courses/forms.py` (`LessonBuilderForm.clean_duration()` o `clean()`), `templates/courses/partials/builder/lesson_form.html:52-60` (asterisco + `required`), `templates/courses/partials/builder/lesson_item.html` (bloque Duración del edit inline: asterisco + `required`) | Rechaza `duration=0`/vacío para video; rechaza para quiz; NO exige para `attendance` (no romper SD#57.1); editar lección legacy con `duration=0` sin cambiarla ahora falla con mensaje claro (no excepción 500) | A1 (mismo archivo, zona adyacente — serializar evita conflicto de merge) | medium | ⏳ pendiente |
| A3 | `Module.duration_hours` (property análoga a `Course.duration_hours`) + contador en vivo de horas (módulo y curso) en el Constructor vía HTMX out-of-band, sin recargar | `apps/courses/models.py` (`class Module`, nueva `@property duration_hours`), `templates/courses/partials/builder/module_card.html` (badge de horas junto a "N lecciones"), `templates/courses/course_builder.html` (badge de horas del curso en `#course-info-card`), `apps/courses/views.py` (`builder_add_lesson`, `builder_edit_lesson`, `builder_delete_lesson`: agregar swap OOB del badge de módulo y curso) | `Module.duration_hours` con 0 lecciones = 0.0; con N lecciones suma y redondea a 1 decimal igual que `Course.duration_hours`; la respuesta HTMX de agregar/editar/eliminar lección incluye el fragmento OOB con el total actualizado | - | medium | ⏳ pendiente |
| A4 | Unificar duración en horas (`duration_hours`) en `course_detail`/`course_list`/`path_detail` (hoy minutos vía `total_duration`); agregar duración —ausente hoy— en `certificate_detail`/`my_certificates`; implementar `LearningPath.duration_hours` correcto (bug del hallazgo 9) | `templates/courses/course_detail.html:22`, `templates/courses/course_list.html:115`, `templates/learning_paths/path_detail.html:24`, `apps/learning_paths/models.py` (nueva `@property duration_hours`, NO reusar `total_duration` roto), `templates/certifications/certificate_detail.html` (nueva fila "Duración" en "Datos del certificado"), `templates/certifications/my_certificates.html` (nueva fila en "Details") | `LearningPath.duration_hours` con 1 curso de duración conocida da el valor correcto (regresión del bug F9); con 0 cursos da 0.0 sin excepción; `certificate_detail.html` renderiza "Duración" cuando el curso tiene `duration_hours>0`; `course_list.html` no rompe con `duration_hours=0` | - | medium | ⏳ pendiente |

No hay Sprint B — todo lo necesario para la v1.0 entra en Sprint A. Ningún
sub-item es `high` ni `epic` (gate de scope P-11 no se dispara), por lo que no
se pide OK de partición a Miguel.

## DAG dependencias
A1 → A2 (mismo archivo `lesson_form.html`, zona adyacente)
A3 → independiente
A4 → independiente
A0 → sin dependencias (aislado, bloqueado por decisión humana, fuera de la
ejecución de este RUN)

## Riesgos y mitigaciones

- **🔴 Riesgo principal — datos legacy**: 21 de 25 lecciones en prod (84%) hoy
  tienen `duration=0`, incluidas 6 de 7 quiz (verificado con `SELECT COUNT(*)
  FILTER (WHERE duration=0) FROM lessons` vía proxy `sd_lms`). Al volver el
  campo obligatorio (A2), **cualquier edición futura** de esas lecciones
  (aunque sea solo cambiar el título) va a rechazarse hasta que también se
  complete una duración válida. No se propone backfill automático (inventaría
  datos de duración que nadie midió) — se documenta el comportamiento y se
  informa a Andrea/cliente en el comentario de cierre para que sepan que
  deberán completar la duración la próxima vez que toquen esas lecciones.
- **Riesgo de scope en `attendance`**: el form de ALTA nunca mostró Duración
  para `attendance` (usa `scheduled_date`), pero el form de EDICIÓN inline
  (`lesson_item.html`) sí la muestra sin condicional. Decisión de diseño
  tomada en este plan: `attendance` queda **excluida** del `clean_duration()`
  obligatorio (coherente con SD#57.1, que ya decidió que `scheduled_date` es
  opcional para asistencia y el campo Duración no aplica al concepto de una
  sesión presencial agendada). F3 debe implementar la exclusión explícita, no
  asumir "todos los tipos" literal.
- **Bug preexistente descubierto (`LearningPath.total_duration`, hallazgo 9)**:
  aggregate roto sobre una property Python. Se corrige como parte de A4 (no es
  scope creep — es la misma property que el issue pide exponer en
  `path_detail.html`), implementando `LearningPath.duration_hours` con un
  aggregate nuevo que SÍ resuelve contra columnas reales
  (`path_courses__course__modules__lessons__duration`).
  `LearningPath.total_duration` (el método roto) se deja intacto — no se toca
  código no relacionado con este issue; solo se evita heredar su bug en la
  property nueva.
- **Riesgo de concurrencia con siblings del RUN**: este RUN despacha 2 issues
  más de SD en paralelo. Ninguno de los sub-items de #62 toca autorización o
  visibilidad de datos compartidos — todos los journeys de este plan fabrican
  su propio curso/módulo/lección `QA_E2E_SD62_*` y limpian al final; el único
  journey que toca un registro preexistente (A2, lección legacy id=98) es
  READ + intento de guardado que se espera FALLE (no muta nada), así que no
  compite con otro sibling.
- **Riesgo de merge A1/A2**: mismo archivo (`lesson_form.html`), zona
  adyacente (líneas 50-60) — se serializa vía dependencia DAG explícita.
- **UI nueva sin DOM construido (Kaizen #74)**: A3 (contador de horas) y la
  porción de A4 que toca `certificate_detail.html`/`my_certificates.html` son
  UI que HOY no existe — los asserts de esos journeys están marcados
  `# RECONCILIAR_DOM` y quedan pendientes de que F3 los ajuste contra el DOM
  real que construya (ver `ui_nueva_reconciliar` en el JSON de salida).
- **🟡 Hallazgo adicional (posible bug preexistente, a confirmar en F3):**
  `builder_edit_lesson` en error re-renderiza `lesson_item.html` completo con
  `hx-swap=outerHTML` (`apps/courses/views.py` ~1470-1483), y ese partial trae
  su propio `x-data="{ editingLesson: false, ... }"` en la raíz del
  componente. Si Alpine reinicializa `editingLesson=false` al hacer el swap,
  el bloque `<template x-if="editingLesson">` que contiene el formulario Y el
  mensaje de error queda **fuera del DOM** — el usuario vería la fila volver a
  modo vista sin ningún error visible, aunque el guardado haya sido
  rechazado. Esto es directamente relevante para A2: hacer `duration`
  obligatorio sin que el error de "por qué no guardó" sea visible en el modo
  de edición inline sería una regresión de UX. El journey `i62_a2_*` (paso de
  la lección legacy #98) lo ejercita con un `wait_for_selector` sobre
  `.alert-error` — si ese wait da timeout, confirma el hallazgo y F3 debe
  resolverlo como parte de A2 (ej. inicializar `editingLesson` en `true`
  cuando el contexto trae `lesson_form.errors`).

## Validación esperada (qa_claude, smoke maestros + journeys específicos)

- Constructor de Curso: `/courses/admin-courses/<id>/builder/` — agregar
  lección tipo Evaluación (Duración visible), guardar con duration=0
  (rechazado), guardar con duration válida (aceptado), contador de horas de
  módulo/curso actualiza sin recargar.
- `/courses/<id>/` (course_detail) y `/courses/` (course_list) — duración en
  horas visible.
- `/learning-paths/<id>/` (path_detail) — duración en horas visible (antes
  rota).
- `/certifications/<id>/` (certificate_detail) y `/certifications/`
  (my_certificates) — nueva fila de duración visible.
- Legacy: lección real id=98 ("Evaluacion seguridad vial", curso 63 módulo
  78, quiz, duration=0 hoy) — editar sin tocar duration debe rechazarse con
  mensaje claro tras A1+A2.
