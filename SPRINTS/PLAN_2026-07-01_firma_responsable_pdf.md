# PLAN — Firma precargada del responsable HSEQ en PDFs de asistencia (issue #51)

**Fecha:** 2026-07-01
**Issue:** [Indunnova16/SD#51](https://github.com/Indunnova16/SD/issues/51)
**Estado:** Planning completado, listo para ejecución

## Contexto

Hoy el PDF de asistencia (`export_attendance_pdf`, SD#33/#40) muestra únicamente
la tabla de firmantes (trabajadores que firman su asistencia en el canvas de
`attendance_lesson.html`). El espacio de "Firma del responsable" queda vacío —
el responsable HSEQ tendría que firmar cada PDF impreso a mano.

Se agrega un campo `signature` al modelo `User` (dibujable en canvas o subible
como imagen desde `/accounts/users/<id>/edit/`), y `export_attendance_pdf`
inyecta automáticamente esa firma en el pie del PDF cuando la lección tiene un
responsable con firma guardada. El trabajador **sigue firmando manual siempre**
(la tabla de firmantes existente no se toca).

**Decisión de diseño heredada de F1 (documentar en el PR):** no existe hoy un
campo/FK formal "responsable de la lección". Se usa `course.created_by` como
responsable por defecto (FK siempre poblado — típicamente el coordinador HSEQ
que crea el curso), con fallback a `lesson.metadata.get("instructor_id")` si
viene seteado explícitamente. Esto evita expandir el scope a una pantalla nueva
de "asignar responsable a la lección" que el issue no pide.

**Decisión de scope (acotar, v1.0 completa igual):** el campo `signature` se
agrega SOLO a `UserEditForm` (edición admin, `/accounts/users/<id>/edit/` —
la única superficie que pide el issue). NO se toca `ProfileForm`
(autogestión `/accounts/profile/edit/`) — fuera de scope explícito del issue;
si Miguel lo pide después, es un follow-up de 1 línea (agregar "signature" a
`ProfileForm.Meta.fields` + sección análoga en su template).

**Gate de scope (P-11):** 5 sub-items, complexity máxima `medium` — 0 `epic`,
0 `high`. No dispara el gate de partición; corre completo en este RUN
(consistente con SCOPE_DECISION del orquestador).

## Sub-items por sprint

### Sprint A (única — v1.0 completa, no se parte)

| # | Sub-item | Archivos | Tests | Dependencias | Complexity | Estado |
|---|---|---|---|---|---|---|
| A1 | Campo `signature` en `User` + migración | `apps/accounts/models.py`, `apps/accounts/migrations/0014_user_signature.py` | `apps/accounts/tests/test_models.py` (campo blank/null OK) | - | low | ⏳ pendiente |
| A2 | UI "Firma del responsable" en `/accounts/users/<id>/edit/` (canvas + upload) | `apps/accounts/forms.py`, `apps/accounts/views.py` (`user_edit`), `templates/accounts/partials/user_form.html` | `apps/accounts/tests/test_views.py` (upload persiste, canvas base64 persiste, sin cambios no borra firma existente) | A1 | medium | ⏳ pendiente |
| A3 | Resolver "responsable de la lección" + inyectar firma en `export_attendance_pdf` | `apps/courses/views.py` (`_build_attendance_summary` o `export_attendance_pdf`) | `apps/courses/tests/test_views.py` (responsable con firma → URL en contexto; sin firma → vacío; fallback `instructor_id`) | A1 | medium | ⏳ pendiente |
| A4 | Sección "Firma del Responsable" en el pie del PDF | `templates/courses/attendance_pdf.html` | (cubierto por smoke E2E — no requiere unit test de template aparte) | A3 | low | ⏳ pendiente |
| A5 | Tests unitarios edge cases + smoke E2E | `apps/accounts/tests/`, `apps/courses/tests/` | happy path + ≥2 edge cases (sin firma, fallback instructor_id) | A2, A3, A4 | low | ⏳ pendiente |

`primer_sub_conjunto_deployable`: A1 (schema aislado, aditivo, sin riesgo — el
resto depende de A1 y se entrega junto en el mismo PR/deploy).

## DAG dependencias

```
A1 → A2
A1 → A3 → A4
A2, A3, A4 → A5
```

## Especificación exacta para F3 (evita drift plan↔código)

### A1 — Modelo

```python
# apps/accounts/models.py, junto a `photo` (línea ~99)
signature = models.ImageField(
    _("Firma"),
    upload_to="users/signatures/",
    blank=True,
    null=True,
)
```

`python manage.py makemigrations accounts` → `0014_user_signature.py`.

### A2 — Form + View + Template

- `apps/accounts/forms.py` → `UserEditForm.Meta.fields`: agregar `"signature"`
  al final de la lista. Widget: `forms.FileInput(attrs={"class": "file-input
  file-input-bordered w-full", "accept": "image/*"})` en el dict `widgets`
  (nombre del campo en el form = nombre del campo del modelo = `signature`,
  NO overridear el `name` del input — el journey depende de
  `input[name="signature"]`).
- `apps/accounts/views.py` → `user_edit()`:
  - **Bug latente que hay que cerrar de paso**: la línea actual
    `form = UserEditForm(request.POST or None, instance=user)` **NO pasa
    `request.FILES`** — sin esto, la subida de imagen (`input[type=file]`)
    nunca llega al form. Cambiar a:
    `form = UserEditForm(request.POST or None, request.FILES or None, instance=user)`.
  - Alterna base64 (canvas): tras `form.is_valid()`, ANTES de `form.save()`
    (o vía `form.save(commit=False)` + asignar + `.save()`), leer
    `request.POST.get("signature_canvas_data")`; si viene con formato
    `data:image/png;base64,...`, decodificar y asignar al `ImageField` con
    `ContentFile` (mismo patrón que `save_attendance_signature` en
    `apps/courses/views.py` línea ~1997-2026). Si NO viene ni archivo ni
    canvas data, el campo se deja intacto (no borrar firma existente por
    default de Django en campos file opcionales no re-enviados).
- `templates/accounts/partials/user_form.html` → nueva sección **"Firma del
  responsable"** (heading `<h3>`, texto exacto — lo assertea el journey),
  después de "Información Laboral" y antes del bloque de contraseña:
  - Preview de la firma actual si `user_obj.signature`: `<img
    src="{{ user_obj.signature.url }}" ...>`.
  - Canvas de dibujo (reusar patrón JS de `templates/courses/
    attendance_lesson.html` líneas ~206-338: mousedown/mousemove/touch,
    `toDataURL` a base64 en un input hidden `name="signature_canvas_data"`),
    con botón "Limpiar".
  - Alternativa "O subir una imagen": `{{ form.signature }}` (el FileInput
    del form — el input real que el journey sube).
  - El `<form>` ya tiene `enctype="multipart/form-data"` (línea 1 actual) —
    no requiere cambio ahí.

### A3 — Resolución de responsable + contexto PDF

```python
# apps/courses/views.py, dentro de export_attendance_pdf() antes de render_to_string
User = get_user_model()  # agregar `from django.contrib.auth import get_user_model` al import
responsable = course.created_by
instructor_id = lesson.metadata.get("instructor_id")
if instructor_id:
    try:
        responsable = User.objects.get(pk=instructor_id)
    except User.DoesNotExist:
        pass
responsable_signature_url = ""
if responsable and responsable.signature:
    try:
        responsable_signature_url = responsable.signature.url
    except Exception:
        responsable_signature_url = ""
```

Agregar `"responsable": responsable, "responsable_signature_url":
responsable_signature_url` al `context` de `render_to_string`.

### A4 — Template PDF

`templates/courses/attendance_pdf.html`, después de la tabla `.signers-table`
y antes de `.footer`:

```html
<div class="section-title">Firma del Responsable</div>
<table class="info-table">
    <tr>
        <td style="width:60%;">
            <div class="label">Responsable</div>
            <div class="value">{{ responsable.get_full_name|default:"—" }}</div>
        </td>
        <td style="width:40%; text-align:center;">
            {% if responsable_signature_url %}
                <img class="signature-img" src="{{ responsable_signature_url }}" alt="Firma del responsable">
            {% else %}
                <div style="border-top: 1px solid #1a1a1a; margin-top: 30px; padding-top: 4px; font-size:8pt; color:#666;">Firma del responsable</div>
            {% endif %}
        </td>
    </tr>
</table>
```

## Riesgos y mitigaciones

- **Riesgo:** `user_edit()` sin `request.FILES` es un bug PRE-EXISTENTE que
  bloquea silenciosamente la subida de imagen si no se corrige junto con A2.
  Mitigación: incluido explícitamente en la spec de A2 arriba (no es opcional).
- **Riesgo:** dejar el campo `signature` intacto cuando el POST no trae ni
  archivo ni canvas data (evitar que el form borre la firma existente en cada
  guardado de otros campos). Mitigación: NO limpiar el campo salvo que venga
  explícitamente vacío/reemplazo — comportamiento default de Django ya lo
  cubre para el `FileField` (no reenviado = se mantiene), solo cuidar que el
  bloque canvas no pise con string vacío.
- **Riesgo bajo — migración:** campo aditivo `blank=True, null=True`, no
  requiere backfill ni afecta filas existentes. Deploya sola, sin downtime.
- **Limitación conocida del harness qa-prod:** no existe una acción declarativa
  para "dibujar" en un `<canvas>` vía Playwright (solo `assert_canvas_painted`
  para verificar que YA se pintó, no para simularlo) ni extracción de texto/
  imagen de un PDF binario. El journey E2E valida el **flujo de subida de
  imagen** (determinístico) + persistencia en BD + crecimiento de tamaño del
  PDF; el flujo de "dibujar en canvas" queda para verificación manual/visual
  puntual (no bloquea el gate).

## Validación esperada (qa_claude smoke maestros)

- `/accounts/users/<id>/edit/` — sección "Firma del responsable" visible,
  subir imagen persiste y se refleja en el preview tras guardar.
- `/courses/<id>/lessons/<id>/attendance/export-pdf/` de un curso cuyo
  `created_by` tiene firma guardada → PDF crece de tamaño (imagen embebida)
  respecto al mismo PDF sin firma.
- Curso cuyo responsable NO tiene firma → PDF sigue generando sin error,
  línea de firma en blanco.
- Instrucciones cliente: "Edite su usuario en Usuarios → (su nombre) →
  Editar, dibuje o suba su firma UNA vez, guarde. Genere el PDF de
  asistencia de cualquier curso que usted haya creado — la firma aparecerá
  automáticamente en el pie."
