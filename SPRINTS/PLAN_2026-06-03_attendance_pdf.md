# PLAN — Attendance Lesson scheduled_date + PDF export + Resumen Admin (bundle SD#33 + SD#40)

**Fecha:** 2026-06-03
**Issues:**
- [Indunnova16/SD#33 — Attendance Lesson Type with PDF Export](https://github.com/Indunnova16/SD/issues/33) (Sprint A)
- [Indunnova16/SD#40 — Resumen de Asistencia para Administrador con PDF descargable](https://github.com/Indunnova16/SD/issues/40) (Sprint B)
**Estado:** Planning completado, listo para ejecución
**Branch:** UNA branch consolidada (los dos issues comparten models/forms/views/urls/templates en apps/courses). #33 primero (provee `scheduled_date`), #40 después (lo consume).

## Contexto

El tipo de lección "Asistencia" ya existe en producción (commit d26aa8a): `Lesson.Type.ATTENDANCE`,
modelo `AttendanceSignature`, `attendance_lesson_view` (views.py:1934), `save_attendance_signature`,
y `templates/courses/attendance_lesson.html` (captura de firma con canvas). Falta cerrar la v1.0
completa de dos features dependientes:

- **SD#33**: campo `Lesson.scheduled_date` (DateTimeField) + integración en course builder
  (LessonBuilderForm + partial lesson_form.html, mostrado solo cuando el tipo es Asistencia) +
  mostrar `scheduled_date` en attendance_lesson.html + vista `export_attendance_pdf` (staff,
  xhtml2pdf) + template `attendance_pdf.html` (lista de firmantes: nombre, cédula, fecha/hora,
  estado, firma) + botón de descarga.
- **SD#40** (depende de #33): resumen de asistencia para administrador con tabla de firmas/estados
  por sesión + **% de asistencia POR SESIÓN** (firmantes / inscritos en el curso) + totales, y el
  PDF incluye nombre + cédula (`document_number`) + fecha + estado + firma. Decisión de scope v1.0
  tomada por Miguel.

### Hechos verificados en el repo (grounding)
- Última migración: `apps/courses/migrations/0016_alter_lesson_lesson_type_attendancesignature.py` → **la nueva es `0017`**.
- Patrón PDF canónico del repo: **xhtml2pdf** `from xhtml2pdf import pisa` → `pisa.CreatePDF(html_string, dest=BytesIO(), encoding="utf-8")` → `HttpResponse(result.getvalue(), content_type="application/pdf")` con `Content-Disposition: attachment` (ver `apps/accounts/views.py:531-573`, vista `export_user_profile_pdf`). weasyprint está en requirements pero el patrón establecido es xhtml2pdf; **usar xhtml2pdf** por consistencia.
- Permiso staff: patrón del repo es `@login_required` + `if not request.user.is_staff: messages.error(...); return redirect(...)` (NO un decorador `@staff_member_required`).
- `User.document_number` existe (`apps/accounts/models.py:93`, es el USERNAME_FIELD). Es la cédula.
- `AttendanceSignature` tiene: `lesson` (FK), `user` (FK), `signature_image` (ImageField), `signature_type` (student/instructor), `instructor` (FK), `signed_at` (auto_now_add). NO tiene campo de "estado". El estado (Presente/Ausente) se deriva: usuario CON firma = Presente; inscrito SIN firma = Ausente.
- Inscritos: `Enrollment.objects.filter(course=course)` con FK `user`. attendance_lesson_view ya usa `Enrollment`.
- Builder: `LessonBuilderForm` (forms.py:365) tiene fields sin scheduled_date. El partial `templates/courses/partials/builder/lesson_form.html` usa Alpine `x-data="{ lessonType: '{{ lesson.lesson_type }}' }"` + `x-model="lessonType"` en el `<select name="lesson_type">`, con bloques `x-show="lessonType === '<tipo>'"` por tipo. El campo scheduled_date va aquí, dentro de `x-show="lessonType === 'attendance'"`.
- Views builder que persisten lección: `builder_add_lesson` (views.py:1138) y `builder_edit_lesson` (1256) usan `LessonBuilderForm(request.POST, request.FILES, instance=...)`. Si scheduled_date entra a Meta.fields, se persiste solo (sin tocar las views).

## Sub-items por sprint

### Sprint A — SD#33 (deployable_solo: false; es la base, pero NO se deploya sola: bundle único)

| # | Sub-item | Archivos | Tests | Dependencias | Estado |
|---|---|---|---|---|---|
| A1 | Modelo + migración: `Lesson.scheduled_date = DateTimeField(null=True, blank=True, verbose_name="Fecha y hora agendada", help_text="Solo para lecciones de Asistencia")`. Una sola migración `0017_lesson_scheduled_date.py`. null/blank=True para no romper lecciones existentes (la obligatoriedad para attendance se valida en el form). | apps/courses/models.py, apps/courses/migrations/0017_lesson_scheduled_date.py | `makemigrations --check` limpio; `migrate` aplica sobre dato legacy sin error | - | ⏳ |
| A2 | Form builder: agregar `"scheduled_date"` a `LessonBuilderForm.Meta.fields` + widget `forms.DateTimeInput(attrs={"type":"datetime-local","class":"input input-bordered w-full"}, format="%Y-%m-%dT%H:%M")` + `input_formats=["%Y-%m-%dT%H:%M","%Y-%m-%d %H:%M:%S"]` en `__init__` (gotcha datetime-local manda `YYYY-MM-DDTHH:MM`). Validación: si `lesson_type == "attendance"` y `scheduled_date` vacío → `forms.ValidationError`. | apps/courses/forms.py | unit: form válido attendance con fecha; inválido attendance sin fecha; válido video sin fecha | A1 | ⏳ |
| A3 | UI builder: en partial `lesson_form.html`, agregar bloque `x-show="lessonType === 'attendance'" x-cloak` con label + `{{ lesson_form.scheduled_date }}` (input datetime-local). NO usar comentarios `{# #}` multilínea dentro de `x-data` (gotcha). | templates/courses/partials/builder/lesson_form.html | (cubierto por journey E2E A) | A2 | ⏳ |
| A4 | Mostrar fecha en attendance_lesson.html: bloque header `{% if lesson.scheduled_date %}<div>Fecha agendada: {{ lesson.scheduled_date|date:"d/m/Y H:i" }}</div>{% endif %}` (formato fijo, NO floatformat → evita coma es-CO). | templates/courses/attendance_lesson.html | (cubierto por journey E2E A) | A1 | ⏳ |
| A5 | Vista `export_attendance_pdf(request, course_id, lesson_id)`: `@login_required` + check `is_staff`; carga course+lesson (lesson_type=ATTENDANCE), inscritos `Enrollment.filter(course=course)`, firmas `AttendanceSignature.filter(lesson=lesson).select_related("user")`. Construye filas: por inscrito → nombre, `document_number`, estado (Presente si firmó / Ausente si no), `signed_at`, url de firma. Renderiza `attendance_pdf.html` con xhtml2pdf `pisa.CreatePDF`. Manejo error `pdf.err` → messages.error + redirect. Filename `asistencia_<lesson.id>_<YYYYMMDD>.pdf`. | apps/courses/views.py | unit: 200 + content-type application/pdf con N firmantes; 302/403 para no-staff; 404 lección no-attendance | A1 | ⏳ |
| A6 | URL: `path("<int:course_id>/lessons/<int:lesson_id>/attendance/export-pdf/", views.export_attendance_pdf, name="export_attendance_pdf")` en apps/courses/urls.py. | apps/courses/urls.py | reverse() resuelve | A5 | ⏳ |
| A7 | Template `attendance_pdf.html`: encabezado (curso, lección, **fecha agendada**, fecha generación), tabla firmantes (nombre, cédula, estado, hora firma, imagen firma), total firmantes, pie. Estilos inline compatibles xhtml2pdf (mismo patrón que `accounts/user_profile_pdf.html`, sin Tailwind). | templates/courses/attendance_pdf.html | (cubierto por A5 unit + journey B) | A5 | ⏳ |
| A8 | Botón "Descargar PDF" en attendance_lesson.html: `{% if request.user.is_staff %}<a href="{% url 'courses:export_attendance_pdf' course.id lesson.id %}" class="btn btn-primary">Descargar PDF</a>{% endif %}`. | templates/courses/attendance_lesson.html | (cubierto por journey E2E A) | A6 | ⏳ |

### Sprint B — SD#40 (deployable_solo: false; consume scheduled_date de Sprint A)

| # | Sub-item | Archivos | Tests | Dependencias | Estado |
|---|---|---|---|---|---|
| B1 | Resumen admin en attendance_lesson_view: cuando `request.user.is_staff`, agregar al context `attendance_summary` = lista de inscritos con {nombre, document_number, estado, signed_at, signature_image}, `total_inscritos`, `total_presentes`, `porcentaje_asistencia` = round(presentes/inscritos*100,1) POR SESIÓN (inscritos del curso). Reusar el queryset de A5 (extraer helper `_build_attendance_rows(course, lesson)` en views.py para no duplicar). | apps/courses/views.py | unit: % correcto con 2/3 firmados = 66.7; 0 inscritos → 0% sin ZeroDivisionError | A1, A5 | ⏳ |
| B2 | UI resumen admin en attendance_lesson.html: bloque `{% if request.user.is_staff and attendance_summary %}` con tabla (nombre, cédula, estado badge Presente/Ausente, hora firma) + totales + % asistencia. Visible solo staff, debajo del área de firma. | templates/courses/attendance_lesson.html | (cubierto por journey E2E A read-only assert) | B1 | ⏳ |
| B3 | PDF resumen: extender `attendance_pdf.html`/vista A5 para incluir el bloque resumen (total inscritos, total presentes, % asistencia, estado por usuario). Como A5/A7 ya recorren inscritos con estado, B3 añade fila de totales + % al template y verifica que cédula+fecha+estado+firma estén en el PDF (requisito explícito SD#40). Misma vista `export_attendance_pdf` sirve a ambos issues (un solo PDF canónico). | templates/courses/attendance_pdf.html, apps/courses/views.py | unit: PDF contiene % y totales (assert por bytes/len + render sin error) | A7, B1 | ⏳ |
| B4 | Tests consolidados: `apps/courses/tests/test_attendance_pdf.py` cubriendo A5+B1+B3 (happy path multi-usuario, permisos no-staff, 404 no-attendance, % por sesión, edge 0 inscritos) contra ≥1 lección/firma legacy si existe en fixtures. | apps/courses/tests/test_attendance_pdf.py | pytest verde, cobertura happy + 3 edge | A5, B1, B3 | ⏳ |

## DAG dependencias

```
A1 (migración scheduled_date)
 ├─→ A2 (form) ─→ A3 (UI builder)
 ├─→ A4 (mostrar fecha attendance_lesson)
 └─→ A5 (vista export PDF) ─→ A6 (URL) ─→ A8 (botón descarga)
                            └─→ A7 (template PDF)

A1,A5 ─→ B1 (resumen context) ─→ B2 (UI resumen admin)
A7,B1 ─→ B3 (PDF resumen totales+%)
A5,B1,B3 ─→ B4 (tests consolidados)
```

Orden de ejecución sugerido (F3 sprint_exec):
1. **A1** primero (migración, bloquea casi todo).
2. Luego en paralelo: rama form/UI (A2→A3, A4) y rama PDF (A5→{A6→A8, A7}).
3. Después Sprint B: B1 → B2; B3 (tras A7+B1); B4 al final.

## Riesgos y mitigaciones

- **Migración duplicada** (gotcha /modulo F3): última es 0016 → la nueva DEBE ser `0017_lesson_scheduled_date`. Una sola migración para todo el bundle. Mitigación: `makemigrations --check` antes de commit; no crear migraciones por sub-item.
- **datetime-local + DateTimeField** (gotcha análogo a input type=month): el widget manda `YYYY-MM-DDTHH:MM`; el DateTimeField default no lo parsea → form inválido en prod. Mitigación: `input_formats` explícito en el form (A2) + `format="%Y-%m-%dT%H:%M"` en el widget para repintar el valor al editar.
- **Coma decimal es-CO en JS/templates**: el `porcentaje_asistencia` se muestra en HTML normal (no en `<script>` inline ni en `<input type=number>`), así que la coma es aceptable visualmente. NO inyectar el % en JS inline. Si se inyectara, usar `|stringformat` / `json.dumps`.
- **xhtml2pdf con imágenes de firma**: las firmas son ImageField en storage (GCS). xhtml2pdf necesita URL/ruta accesible; el patrón user_profile_pdf no embebe imágenes de storage remoto. Mitigación: usar `signature.signature_image.url`; si xhtml2pdf no resuelve el remoto, degradar a "Firmado ✓ (ver app)" en el PDF (el dato legal es estado+fecha+cédula, no la imagen pixel-perfect). Documentar al cliente.
- **% por sesión definición**: scope fijado por Miguel = firmantes / inscritos en el curso. NO cambiar a "llamados de esa sesión" sin nuevo OK.
- **Estado derivado, no persistido**: AttendanceSignature no tiene campo estado. Presente = tiene firma; Ausente = inscrito sin firma. v1.0 no soporta "Tardío" (requeriría comparar signed_at vs scheduled_date; fuera de scope salvo OK). El F1 de #40 listaba "Tardío" pero el scope confirmado por Miguel es Presente/Ausente.

## Validación esperada (qa_claude smoke maestros)

Usuario QA prod: ver memoria `sdchecklist_qa_user` / `SDCheckList QA user prod` — `qa_claude` superuser+staff en `auth_user` de `sdchecklist_db`, login django-allauth `/accounts/login/` (campo form `login`), pwd `ClaudeQA2026!`.
**Nota:** confirmar en F1/F3 que el repo `SD` corresponde al service/db de SDCheckList (mismo aplicativo) o ajustar credencial al QA user real de SD antes del smoke.

Smoke / journeys (ver journeys/SD_3340.yaml):
- (a) Builder: crear lección tipo Asistencia con `scheduled_date` → guardar → reabrir builder y verificar que la fecha persiste.
- (b) Descargar PDF de asistencia (`/courses/<course>/lessons/<lesson>/attendance/export-pdf/`) → HTTP 200, content-type application/pdf, tamaño mínimo razonable.
- Crawl maestros post-deploy: lista cursos + detalle curso + builder + attendance_lesson (HTTP 200 en todo), incluyendo ≥1 lección attendance pre-deploy.

## Instrucciones de validación cliente (para comentario F6)

1. Course builder → crear lección, tipo **Asistencia** → aparece campo **Fecha y hora agendada** (obligatorio) → guardar.
2. Abrir la lección de Asistencia → se ve la fecha agendada en el encabezado; los estudiantes firman.
3. Como administrador: en la misma lección ver el **resumen de asistencia** (tabla con nombre, cédula, estado Presente/Ausente, hora, % de asistencia y totales).
4. Botón **Descargar PDF** → descarga el PDF con encabezado (curso, lección, fecha), lista de firmantes (nombre, cédula, fecha, estado, firma), totales y % de asistencia.
