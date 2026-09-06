# PLAN — Certificados (logo/horas/firma) + RBAC asistencia Coordinador (issue #59)

**Fecha:** 2026-07-09
**Issue:** [Indunnova16/SD#59](https://github.com/Indunnova16/SD/issues/59)
**Estado:** Planning completado (F2), listo para ejecución (F3)

## Contexto

El cliente reportó 2 PDFs con problemas: (1) el **certificado** de curso muestra
"N/A horas" en vez de la duración real, no tiene el logo institucional "SD S.A.S."
(cae al fallback de texto "SD") y firma con un nombre fijo "Directora HSEQ" en vez
de la persona real que asignó el curso; (2) el **PDF/vista de asistencia** está
restringido a Administrador y el cliente pide que Coordinador también pueda verlo
y exportarlo (Ejecutor/aprendiz sigue solo firmando, eso ya está bien).

**Gate humano post-F1 (Miguel, 2026-07-09):** de los 5 sub-items que F1 identificó,
el 5º (cambio de FORMATO del PDF de asistencia) queda **FUERA de este sprint** — los
2 adjuntos "actual"/"deseado" del issue son el mismo archivo byte a byte (MD5
`dcb06960b402747d73a569594294ac60` idéntico), no hay fuente de verdad para inferir
qué cambia. Se documenta como pendiente de aclaración del cliente (ver sección
"Fuera de este sprint" abajo) y como pregunta explícita para el comentario de cierre
(F6). Los otros 4 sub-items SÍ tienen causa raíz clara en código y entran a la v1.0
de este sprint.

**Verificación BD prod (F2, antes de codear — proxy 127.0.0.1:5434/sd_lms):**
- `SELECT COUNT(*) FROM certificate_templates` → **0 filas**. Confirma la hipótesis
  de F1: no solo falta una plantilla *activa*, no existe NINGUNA fila — cero riesgo
  de colisión al sembrar la plantilla oficial con el logo real (A2).
- `duration_hours` real por curso (no solo el de prueba "prueba3"):
  `01_PODA Y TALA`(id=63)=0.3h, `prueba`(id=64)=0.0h, `prueba 2`(id=68)=0.2h,
  `prueba 2 - 07`(id=76)=0.0h, `prueba3`(id=78)=0.0h, **`02_VIAL` / INDUCCIÓN
  SEGURIDAD VIAL (id=79)=0.0h — curso REAL (no de prueba), con certificado YA
  EMITIDO (id=28, user_id=3)**. Confirma que el bug de "N/A" no es solo cosmético
  de datos de prueba: ya afectó un certificado real entregado a un trabajador.

## Sub-items — Sprint A (v1.0 completa, un solo PR/deploy)

**⚠️ Recomendación de ejecución para F3:** las 3 sub-items de certificado (A1, A2,
A3) tocan el **mismo archivo** `certificate_template.html` en bloques distintos
(duración / logo / firma). Ejecutarlas en branches/worktrees paralelas dispara el
gotcha ya documentado de "un issue partido en varias branches por sub-feature"
(memoria `gotcha_run_autonomo_split_branches_por_subfeature`, caso real Instelec#147
donde se perdió parte del fix al no revisar todas las branches). **Recomendación:
1 solo agente/worktree para A1→A2→A3 en secuencia**, A4 sí puede correr en paralelo
(archivos distintos: `apps/courses/*`). Es una recomendación de **orden de
ejecución interno**, no una entrega parcial al cliente — las 4 sub-items se
despliegan juntas en el mismo PR.

| # | Sub-item | Archivos | Tests | Dependencias | Complexity | Estado |
|---|---|---|---|---|---|---|
| A1 | Certificado: horas reales — reemplazar `\|default:"N/A"` (trata 0.0 como falso) por comparación explícita contra `None` | `apps/certifications/templates/certifications/certificate_template.html` | `apps/certifications/tests/test_issue_59.py` (0.0h muestra "0.0 horas", no "N/A"; valor positivo sigue mostrando bien) | - | low | ⏳ pendiente |
| A2 | Certificado: `template_file` opcional (migración schema) + sembrar y activar la plantilla oficial con el logo real "SD S.A.S." (migración de datos, embebe el PNG del adjunto del cliente) | `apps/certifications/models.py`, `apps/certifications/migrations/0003_alter_certificatetemplate_template_file_optional.py`, `apps/certifications/migrations/0004_seed_default_certificate_template.py`, `apps/certifications/migrations/assets/sd_sas_logo.png` (nuevo, copiado del adjunto) | `apps/certifications/tests/test_issue_59.py` (form/model validan sin `template_file`; certificado nuevo hereda `template` activo con logo) | A1 (mismo archivo, ejecutar en secuencia) | medium | ⏳ pendiente |
| A3 | Certificado: firma dinámica = nombre + firma de quien asignó el curso (`Enrollment.assigned_by`), con fallback a `course.created_by` cuando el auto-asignado es el mismo destinatario (auto-inscripción) o `assigned_by` es nulo — reemplaza el `template.signer_name`/`signature_image` estático | `apps/certifications/services.py`, `apps/certifications/templates/certifications/certificate_template.html` | `apps/certifications/tests/test_issue_59.py` (prioriza `assigned_by`; fallback auto-inscripción; fallback `assigned_by=None`; con/sin imagen de firma) | A2 (mismo archivo, ejecutar en secuencia) | medium | ⏳ pendiente |
| A4 | Asistencia: ampliar `attendance_lesson_view` + `lesson_view` (roster embebido) + `export_attendance_pdf` de Administrador-only a Administrador+Coordinador — **sin tocar `_staff_required`** (compartido con 9 vistas más). **Incluye 2 hallazgos de F2 no capturados por F1**: el roster NO se muestra solo por rol en la vista — hay un segundo gate independiente `{% if request.user.is_staff %}` en **2 templates** (`attendance_lesson.html:128` y `lesson_view.html:328`, bloque duplicado) que seguiría bloqueando a Coordinador aunque la vista se arregle sola | `apps/courses/views.py` (`attendance_lesson_view`, `lesson_view`, nuevo helper `_attendance_export_required`), `templates/courses/attendance_lesson.html`, `templates/courses/lesson_view.html` | `apps/courses/tests/test_issue_59_a4.py` (Coordinador ve roster en ambas superficies + exporta PDF; Ejecutor sigue bloqueado en ambas — regresión) | - | medium | ⏳ pendiente |

`primer_sub_conjunto_deployable`: `["A1", "A4"]` — A1 es la más aislada/segura del
grupo certificado y A4 está en un archivo completamente distinto (`apps/courses/*`),
así que son el par seguro para arrancar en paralelo; A2 y A3 siguen en secuencia
sobre la misma rama que A1 (ver recomendación de ejecución arriba).

## Fuera de este sprint (bloqueado — pendiente cliente)

| # | Sub-item | Motivo del bloqueo | Acción |
|---|---|---|---|
| D1 | Asistencia: cambio de FORMATO del PDF (`templates/courses/attendance_pdf.html`) | Los 2 adjuntos "actual" (`att_02.pdf`) y "deseado" (`att_04.pdf`) del issue son **el mismo archivo byte a byte** (MD5 `dcb06960b402747d73a569594294ac60` idéntico en ambos, distintos asset id de GitHub pero contenido igual). No hay fuente de verdad para inferir el cambio pedido — no se adivina. | Pregunta explícita al cliente en el comentario de cierre (F6): "¿cuál es el cambio de formato exacto? ¿Agregar info de presentación/resultado de examen (score, intento) cuando la lección de asistencia está ligada a una evaluación, o es un cambio de diseño/layout distinto?" |

## DAG dependencias

```
A1 → A2 → A3   (secuencial, mismo archivo certificate_template.html — 1 solo worktree)
A4             (independiente, apps/courses/* — puede correr en paralelo a la cadena A1-A3)
```

## Especificación exacta para F3 (evita drift plan↔código)

### A1 — `certificate_template.html` línea 175

Actual:
```html
con una duraci&oacute;n de
<strong>{{ course.duration_hours|default:"N/A" }} horas</strong>
```

Nuevo (Django 5.1 soporta `is not None` en `{% if %}` — confirmado, repo usa
Django 5.1.15):
```html
con una duraci&oacute;n de
<strong>{% if course.duration_hours is not None %}{{ course.duration_hours }}{% else %}N/A{% endif %} horas</strong>
```

Nota: `Course.duration_hours` (property, `apps/courses/models.py:289`) NUNCA
retorna `None` en la práctica (`round(total_duration/60, 1)`, `total_duration`
nunca es `None`) — el fix hace que el número real (incluido `0.0`) se muestre
siempre; "N/A" queda como salvaguarda defensiva si `course` no resuelve la
property por algún motivo futuro, no como comportamiento esperado hoy.

### A2 — Modelo + 2 migraciones + asset

**Modelo** (`apps/certifications/models.py`, campo `template_file` ~línea 23):
```python
template_file = models.FileField(
    _("Archivo de plantilla"),
    upload_to="certificates/templates/",
    blank=True,  # <-- agregar (permite crear una plantilla "solo logo/firma")
    help_text=_(
        "Archivo HTML/PDF de la plantilla (opcional — si se deja vacío, "
        "se usa la plantilla por defecto del sistema con el logo/firma "
        "configurados)"
    ),
    validators=[validate_certificate_template_extension],
)
```
**NO se requiere tocar `apps/certifications/forms.py` ni `admin.py`** — verificado:
`CertificateTemplateForm` (ModelForm plano, sin `Meta.required` ni overrides) y
`CertificateTemplateAdmin` (sin fieldsets propios) derivan el "requerido" del
`blank` del modelo automáticamente. F1 los había listado como "a tocar"; no hace
falta.

**Asset**: copiar el logo real que subió el cliente (adjunto del issue, ya
revisado por F1) desde `$RUN_DIR/attachments/SD_59/att_03.png`
(`/Users/miguelrodriguez/Desktop/Repos/SPRINTS/RUN_2026-07-09_2048/attachments/SD_59/att_03.png`
— MD5 `fda0eb21a8e7bb8737b82fe44389f03b`, PNG 1800×915 RGBA, 192KB, fondo
transparente) a `apps/certifications/migrations/assets/sd_sas_logo.png` (nuevo
directorio). El CSS ya limita el render (`​.logo img { max-height: 22mm; max-width:
60mm; }`) — no hace falta recortar/optimizar el PNG fuente.

**Migración 0003** (schema, `AlterField`): el `blank=True` de arriba.

**Migración 0004** (datos, `RunPython`, idempotente):
```python
from pathlib import Path
from django.core.files.base import ContentFile
from django.db import migrations

LOGO_PATH = Path(__file__).resolve().parent / "assets" / "sd_sas_logo.png"
TEMPLATE_NAME = "SD S.A.S. — Plantilla Oficial (Logo)"


def seed_template(apps, schema_editor):
    CertificateTemplate = apps.get_model("certifications", "CertificateTemplate")
    if CertificateTemplate.objects.filter(name=TEMPLATE_NAME).exists():
        return
    tpl = CertificateTemplate(
        name=TEMPLATE_NAME,
        description="Plantilla sembrada por SD#59 — logo institucional real, "
        "sin archivo de plantilla completo (usa el default con "
        "firma dinámica de #59/A3).",
        is_active=True,
    )
    tpl.logo.save("sd_sas_logo.png", ContentFile(LOGO_PATH.read_bytes()), save=True)


def unseed_template(apps, schema_editor):
    CertificateTemplate = apps.get_model("certifications", "CertificateTemplate")
    CertificateTemplate.objects.filter(name=TEMPLATE_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [("certifications", "0003_alter_certificatetemplate_template_file_optional")]
    operations = [migrations.RunPython(seed_template, unseed_template)]
```

**Efecto**: `CertificateService.issue_certificate` ya hace
`CertificateTemplate.objects.filter(is_active=True).first()` — al existir esta
fila, TODO certificado nuevo la usa automáticamente. Como `template_file` queda
vacío, `_generate_pdf` sigue cayendo al `else` (renderiza el `certificate_template.html`
por defecto — el mismo que arregla A1/A3), pero ahora `template` NO es `None` en
ese contexto ⇒ `{% if template and template.logo %}` en la plantilla muestra el
logo real en vez del fallback de texto "SD".

### A3 — Firma dinámica (`services.py` + `certificate_template.html`)

**Nuevo helper** en `apps/certifications/services.py` (mismo patrón que
`_resolve_attendance_responsable` de `apps/courses/views.py`, issue #51):
```python
def _resolve_certificate_signer(certificate):
    """Resuelve quién firma el certificado: el coordinador que ASIGNÓ el curso
    (Enrollment.assigned_by), con fallback a course.created_by cuando
    assigned_by es nulo o es la MISMA persona que recibe el certificado
    (auto-inscripción vía courses:enroll / learning_paths — ahí assigned_by
    queda en request.user, que es el propio estudiante, no un coordinador real).
    """
    from apps.courses.models import Enrollment

    enrollment = Enrollment.objects.filter(user=certificate.user, course=certificate.course).first()
    signer = None
    if (
        enrollment
        and enrollment.assigned_by_id
        and enrollment.assigned_by_id != certificate.user_id
    ):
        signer = enrollment.assigned_by
    if not signer:
        signer = certificate.course.created_by  # NOT NULL, on_delete=PROTECT — siempre poblado

    signature_url = ""
    if signer and signer.signature:
        try:
            signature_url = signer.signature.url
        except Exception:
            signature_url = ""
    return signer, signature_url
```

**`_generate_pdf`** (`services.py`, dict `context` ~línea 228): agregar
```python
signer, signer_signature_url = CertificateService._resolve_certificate_signer(certificate)
context["responsable_nombre"] = signer.get_full_name() if signer else None
context["responsable_cargo"] = getattr(signer, "job_position", "") if signer else ""
context["responsable_signature_url"] = signer_signature_url
```

**Template** (`certificate_template.html` líneas 179-190), reemplazar el bloque
`.signature-block` completo:
```html
<div class="signature-block">
    {% if responsable_signature_url %}
        <img src="{{ responsable_signature_url }}" alt="Firma" class="signature-img">
    {% endif %}
    <div class="signature-line"></div>
    <div class="signer-name">{{ responsable_nombre|default:"—" }}</div>
    <div class="signer-title">{{ responsable_cargo }}</div>
</div>
```
Se elimina el hardcode `Directora HSEQ` y la dependencia de
`template.signer_name`/`template.signature_image` (quedan sin uso para el
certificado por defecto — los campos del modelo `CertificateTemplate` no se
borran, siguen existiendo para plantillas HTML personalizadas vía
`template_file`, que renderizan aparte y no pasan por este bloque).

### A4 — RBAC asistencia (2 vistas + nuevo helper + 2 templates)

**`apps/courses/views.py::attendance_lesson_view`** (~línea 2021): cambiar
```python
if user_has_rol(request.user, Rol.ADMINISTRADOR):
```
por
```python
is_attendance_admin_view = user_has_rol(request.user, Rol.ADMINISTRADOR, Rol.COORDINADOR)
context["is_attendance_admin_view"] = is_attendance_admin_view
if is_attendance_admin_view:
    summary = _build_attendance_summary(course, lesson)
    context.update({...})  # igual que hoy
```
(`is_attendance_admin_view` se agrega SIEMPRE al context, no solo dentro del if —
la plantilla lo necesita como flag booleano confiable, ver abajo).

**`apps/courses/views.py::lesson_view`** (~línea 281, bloque `attendance_context`):
mismo cambio — `user_has_rol(request.user, Rol.ADMINISTRADOR)` →
`user_has_rol(request.user, Rol.ADMINISTRADOR, Rol.COORDINADOR)`, agregando
`"is_attendance_admin_view": is_attendance_admin_view` a `attendance_context`
(siempre, no solo cuando es True — mismo motivo).

**`apps/courses/views.py::export_attendance_pdf`** (~línea 2252): reemplazar
```python
if err := _staff_required(request):
    return err
```
por un helper NUEVO (NO modificar `_staff_required`, compartido con 9 vistas más):
```python
def _attendance_export_required(request):
    """Check ADMINISTRADOR u COORDINADOR — helper propio de asistencia (SD#59),
    NO reusar/ampliar _staff_required (compartido con 9 vistas más del builder)."""
    if not user_has_rol(request.user, Rol.ADMINISTRADOR, Rol.COORDINADOR):
        if request.headers.get("HX-Request"):
            return JsonResponse({"error": "No autorizado"}, status=403)
        messages.error(request, "No tiene permisos para acceder a esta pagina.")
        return redirect("courses:list")
    return None
```
y en `export_attendance_pdf`: `if err := _attendance_export_required(request): return err`.

**`templates/courses/attendance_lesson.html` línea 128** y
**`templates/courses/lesson_view.html` línea 328** (bloque duplicado, mismo
"Resumen de asistencia" + botón "Descargar PDF" + tabla): cambiar
```html
{% if request.user.is_staff %}
```
por
```html
{% if is_attendance_admin_view %}
```
**Por qué este cambio es obligatorio y no cosmético**: estos 2 templates gatean
el bloque por `request.user.is_staff` de forma INDEPENDIENTE de lo que la vista
decide poblar en el contexto. `is_staff` se auto-asigna solo para
`job_profile.code == "ADMINISTRADOR"` (decisión #58 #2: `rol` y `is_staff` están
desacoplados a propósito) — un Coordinador real (`rol=COORDINADOR`) casi nunca
tiene `is_staff=True`. Si solo se arregla la vista (como F1 asumió), Coordinador
seguiría sin ver el bloque en AMBAS superficies porque el template lo esconde
por su cuenta. Este hallazgo es de F2, no estaba en el `tocaria` original de F1.

## Riesgos y mitigaciones

- **Riesgo — mismo archivo en 3 sub-items (A1/A2/A3).** Mitigación: DAG
  secuencial explícito arriba + recomendación de 1 solo worktree para la cadena
  certificado, evitando el gotcha de branches-por-subfeature.
- **Riesgo — auto-inscripción hace `Enrollment.assigned_by == certificate.user`.**
  `courses:enroll` y `learning_paths` auto-inscripción setean
  `assigned_by=request.user` (el propio estudiante), no un coordinador real. Sin
  el guard `assigned_by_id != certificate.user_id` en A3, un certificado de
  auto-inscripción mostraría al propio estudiante "firmando" su certificado.
  Mitigado con el fallback a `course.created_by` (mismo patrón ya probado en
  `_resolve_attendance_responsable`, #51) — `Course.created_by` es
  `on_delete=PROTECT` sin `null=True`, siempre poblado, y `course_create` es
  vista staff-only, así que siempre es una identidad administrativa razonable.
- **Riesgo bajo — colisión con SD#58 (mismo RUN).** SD#58 toca
  `apps/accounts/views.py` + `apps/accounts/backends.py` (capa de login). A4 de
  este issue toca `apps/courses/views.py` + 2 templates de `templates/courses/`
  (capa de autorización de un módulo distinto). Archivos disjuntos — riesgo bajo,
  vigilar igual en F4 por si el merge del RUN los junta en la misma integración.
- **Limitación conocida del harness qa-prod (igual que #51):** no hay acción para
  extraer texto/imagen de un PDF binario. Los journeys de A1/A2/A3 validan que la
  generación del certificado **no se rompe** (200, `application/pdf`, tamaño
  mínimo razonable) end-to-end contra un curso real con duración 0 — la
  aserción de TEXTO exacto ("0.0 horas" vs "N/A", el logo, el nombre del firmante)
  vive en los tests unitarios (`render_to_string`/`Template().render()` directo),
  que sí pueden leer el HTML antes de convertirlo a PDF. Instrucción de
  validación manual para Miguel/cliente incluida abajo.
- **Hallazgo fuera de scope, no corregido acá (documentado, no bloquea):**
  `CertificateTemplateService.preview_template` (vista
  `certifications:template_preview`, panel admin de plantillas) NO pasa el
  objeto `template` al contexto de render — el preview de logo/firma de CUALQUIER
  plantilla siempre cae al fallback "SD" / sin firma, independientemente del
  logo real cargado. Es un bug preexistente, adyacente pero no lo que el cliente
  reportó (el cliente se queja del certificado REAL, no de la herramienta de
  preview del panel admin). No se toca en este sprint — si Miguel quiere que el
  preview también se arregle, es un follow-up de 1 línea (pasar `"template":
  template` al `default_data` en `preview_template`).

## Validación esperada (qa_claude smoke + instrucciones cliente)

- **A1**: certificado generado para un curso con `duration_hours` real (incl.
  casos de 0.0h) — la sección "duración" del certificado muestra el número real,
  nunca "N/A" salvo error real de datos.
- **A2**: cualquier certificado nuevo trae el logo institucional "SD S.A.S." en
  vez del fallback de texto rojo "SD".
- **A3**: la firma del certificado muestra el nombre (y firma, si la tiene
  cargada en su perfil vía `/accounts/users/<id>/edit/`) del coordinador que
  asignó el curso — no más "Directora HSEQ" fijo.
- **A4**: Coordinador ve el resumen de asistencia (roster + botón "Descargar
  PDF") tanto en `/courses/<id>/lessons/<id>/attendance/` como navegando la
  lección normal (`/courses/<id>/lessons/<id>/`), y puede exportar el PDF.
  Ejecutor/aprendiz sigue sin verlo (regresión).
- **Instrucciones cliente (para el comentario de cierre F6):** "Genere un
  certificado nuevo completando un curso (o pídanos regenerar uno existente) —
  debe mostrar el logo, la duración real y la firma de quien le asignó el
  curso. Para asistencia: ingrese con un usuario Coordinador a la lección de
  asistencia de cualquier curso — ahora debe ver el resumen y poder descargar
  el PDF, igual que Administrador."
- **Pregunta pendiente (D1, formato asistencia):** incluir en el comentario de
  cierre — ver sección "Fuera de este sprint" arriba.
