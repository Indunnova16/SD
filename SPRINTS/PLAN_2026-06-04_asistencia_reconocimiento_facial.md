# PLAN — Asistencia con reconocimiento facial en SD (port desde Logisticacargues)

**Fecha:** 2026-06-04
**Repo destino:** Indunnova16/SD (`~/Desktop/Repos/SD`, service Cloud Run `sd-lms`)
**Repo origen:** Indunnova16/Logisticacargues (`apps/attendance`)
**Tipo:** Feature nueva (app `apps.attendance`) — requiere migraciones + nueva dependencia (boto3) + credenciales AWS.

## Decisiones tomadas (Miguel, 2026-06-04)
1. **Flujo:** check-in / check-out **diario** independiente del LMS (igual a Logística). NO se integra a `courses.AttendanceSignature` ni a `preop_talks.TalkAttendee`.
2. **Verificación:** **kiosko 1:N público** (sin login). La cámara identifica a quien aparezca buscando en la collection Rekognition.
3. **Backend IA:** **AWS Rekognition** (reusar `services_rekognition.py` casi verbatim; GCP no ofrece face-matching de identidad).

### F0 resuelto (Miguel, 2026-06-04)
4. **Credenciales AWS:** **mismas de Logisticacargues** (misma cuenta AWS, región `us-east-1`). En Logística viven en GCP Secret Manager como `logisticacargues-aws-access-key-id` / `logisticacargues-aws-secret-access-key`. Para SD: crear `sd-lms-aws-access-key-id` / `sd-lms-aws-secret-access-key` en Secret Manager **con el mismo valor** e inyectarlas en `deploy.yml` vía `--update-secrets` (o referenciar directo los secrets de logística si el SA de sd-lms tiene acceso).
5. **Collection propia de SD:** `sd-lms-employees` (misma cuenta AWS, namespace aislado). NO reusar `logisticacargues-employees` para no mezclar rostros de los dos aplicativos. `ExternalImageId = user.id` mantiene la separación lógica.
6. **Privacidad/biometría:** aceptado el tratamiento de datos sensibles (Ley 1581 / Habeas Data). Pendiente operativo: consentimiento + política de retención de `FaceCheckEvent.selfie` (ver Riesgos).
7. **Día laboral configurable:** `_work_day_date` NO hardcodea las 22:00. Setting `ATTENDANCE_WORKDAY_ROLLOVER_HOUR` (default `None` = el día laboral = día calendario; valor `22` replica el turno noche de Logística).

## Decisión de diseño por defecto (Miguel puede revertir antes de F1)
- **El "empleado" = `accounts.User`.** SD ya modela al personal operativo en `User` (`document_number`=cédula, `photo`, `status`). En vez de portar el modelo `Employee` de Logística, se extiende `User` con `aws_face_id` + `face_indexed_at` y se usa `User.photo` como foto de referencia.
  - *Alternativa si no se quiere tocar `accounts`:* `FaceProfile(OneToOne→User)` dentro de `apps.attendance` (autocontenido, sin migración de accounts). **Recomendado: extender User** (más simple, una sola identidad).
- **NO se portan:** `WorkCenter`, `JobPosition`, `SchedulePeriod`, `ScheduleLine`, `ShiftAssignment`, `PPEType`, `PPEDelivery`. Son la maquinaria de RR.HH./turnos de Logística, fuera del alcance "asistencia con reconocimiento".
- **Modelos que SÍ se portan:** `AttendanceRecord` (retargeted Employee→User) + `FaceCheckEvent` (auditoría).

## Diferencias clave origen→destino (por qué NO es copy-paste)
| Aspecto | Logisticacargues | SD | Acción |
|---|---|---|---|
| Identidad | `Employee` (modelo propio, `reference_photo`) | `User` (`photo`, `document_number`) | Extender User; referencia = `User.photo` |
| BaseModel | `apps.core.models.BaseModel` **con `is_active`** | `BaseModel` solo timestamps | Filtrar por `User.is_active`/`status`, no por BaseModel |
| Permisos | `ModulePermissionMixin` + `Permission` | `is_staff` / `Role` / allauth | Reemplazar por `LoginRequiredMixin + UserPassesTestMixin(is_staff)` |
| Media | local / S3 | GCS (`django-storages[google]`) | Selfies escriben a GCS por default (sin cambios de código) |
| boto3 | en requirements | **ausente** | Agregar `boto3` a `requirements/base.txt` |
| URLs | `apps.attendance.urls` | web + `api/` por app | Registrar `attendance/` en `config/urls.py` (solo web por ahora) |

## Fases

### F0 — Issue + grounding (antes de tocar código) ✅ resuelto
- [ ] Crear/ubicar issue en `Indunnova16/SD` para trazabilidad ("Asistencia con reconocimiento facial — kiosko diario").
- [x] Credenciales AWS: mismas de Logística (decisión #4). Replicar valores a secrets `sd-lms-aws-*`.
- [x] Día laboral configurable vía `ATTENDANCE_WORKDAY_ROLLOVER_HOUR` (decisión #7).

### F1 — Scaffolding de la app `apps.attendance`
- [ ] `apps/attendance/{__init__,apps,models,services,services_rekognition,views,urls,admin}.py` + `migrations/`, `tests/`, `templatetags/`.
- [ ] Registrar `"apps.attendance"` en `LOCAL_APPS` (`config/settings/base.py`).
- [ ] `AttendanceConfig` con `default_auto_field` y `name = "apps.attendance"`.

### F2 — Modelos + migraciones
- [ ] `apps/accounts`: agregar a `User` → `aws_face_id = CharField(max_length=64, blank=True)`, `face_indexed_at = DateTimeField(null=True, blank=True)`. Migración `accounts/XXXX_user_face_fields.py` (`null/blank`, no rompe legacy).
- [ ] `apps/attendance/models.py`:
  - `AttendanceRecord(BaseModel)`: `user(FK→accounts.User)`, `date(db_index)`, `check_in/out(TimeField null)`, `hours_worked(Decimal null)`, `is_absent`, `absence_reason`, `notes`, `registered_by(FK→User null)`. `unique_together = [user, date]`.
  - `FaceCheckEvent(BaseModel)`: `user(FK null)`, `attendance_record(FK null)`, `kind(check_in/out)`, `status(matched/low_confidence/no_match/no_face/error)`, `selfie(ImageField upload_to="attendance/selfies/%Y/%m/%d/")`, `similarity(Decimal)`, `aws_face_id`, `latitude/longitude(Decimal)`, `user_agent`, `ip_address`, `error_message`. Índices `-created_at` y `(status,-created_at)`.
- [ ] `migrate --check` limpio (gotcha `/modulo` F3: una sola leaf migration por app).

### F3 — Servicios
- [ ] `services_rekognition.py`: copiar verbatim de Logística y retargetear:
  - `Employee` → `accounts.User`; `ExternalImageId = str(user.id)`; búsqueda por `pk` y fallback por `aws_face_id`; filtrar `is_active=True`.
  - `index_employee_face(user)` lee `user.photo` (no `reference_photo`).
  - Mantener: `ensure_collection`, `remove_employee_face`, `search_face`, manejo `MissingReferencePhotoError`/`NoFaceDetectedError`/`RekognitionError`, borrado de cara previa solo tras indexar la nueva.
- [ ] `services.py`: `AttendanceService.check_in/check_out` retargeted a `User`. Conservar cálculo de `hours_worked`. `_work_day_date` lee `settings.ATTENDANCE_WORKDAY_ROLLOVER_HOUR` (None = día calendario; 22 = turno noche).

### F4 — Settings + dependencias
- [ ] `config/settings/base.py`: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION` (def `us-east-1`), `REKOGNITION_COLLECTION_ID` (def `sd-lms-employees`), `REKOGNITION_MATCH_THRESHOLD` (def 90), `ATTENDANCE_WORKDAY_ROLLOVER_HOUR` (def `None`) vía `config()`.
- [ ] `requirements/base.txt`: `boto3==1.35.92` (Pillow ya presente).
- [ ] `.env.example`: documentar las 6 variables nuevas (la sección AWS ya existe, hoy solo para S3).
- [ ] Secret Manager: crear `sd-lms-aws-access-key-id` / `sd-lms-aws-secret-access-key` con el **mismo valor** que los secrets `logisticacargues-aws-*`.
- [ ] `deploy.yml`: `--update-secrets=...,AWS_ACCESS_KEY_ID=sd-lms-aws-access-key-id:latest,AWS_SECRET_ACCESS_KEY=sd-lms-aws-secret-access-key:latest` + env planas `AWS_REGION`/`REKOGNITION_COLLECTION_ID=sd-lms-employees`/`REKOGNITION_MATCH_THRESHOLD=90` (patrón idéntico al deploy de Logística).

### F5 — Vistas + templates + URLs
- [ ] `MobileFaceCheckInView` (público, sin login): GET pinta cámara; POST recibe `selfie`+`kind`+`lat/lng` → `RekognitionService.search_face` → crea `FaceCheckEvent` + `AttendanceService.check_in/out` → JSON. Copiar y retargetear.
- [ ] `MobileFaceQRView` (staff): QR a la URL pública.
- [ ] `FaceEventListView` (staff, auditoría): filtros por estado/tipo/fecha + stats hoy/semana. Swap `ModulePermissionMixin` → `LoginRequiredMixin + UserPassesTestMixin(is_staff)`.
- [ ] Indexado de rostros: **management command** `index_faces` (bulk: recorre `User.is_active` con `photo` y sin `aws_face_id`) + **vista staff** `UserReindexFaceView` (single). En SD la referencia es `User.photo` → opción de **signal** `post_save` en User cuando cambia `photo` (evaluar; el bulk command es el mínimo viable).
- [ ] Templates a `templates/attendance/`: `mobile_face_checkin.html`, `mobile_face_qr.html`, `face_event_list.html`. Adaptar a base de SD (Tailwind/DaisyUI + HTMX) y nav. **Gotchas SD:** no `{# #}` multilínea en `x-data`; floats Django en JS inline con `|stringformat`/`json.dumps` (es-CO coma).
- [ ] `apps/attendance/urls.py` (`app_name="attendance"`) con: `marcacion-movil/`, `marcacion-movil/qr/`, `eventos-faciales/`, `usuarios/<pk>/reindexar-rostro/`.
- [ ] `config/urls.py`: `path("attendance/", include("apps.attendance.urls"))`.

### F6 — Tests
- [ ] Portar `test_mobile_face_checkin.py` (mock de `RekognitionService.search_face`) retargeteado a User.
- [ ] Servicio: tests de `index_employee_face` / `search_face` con `boto3` mockeado (sin llamadas reales).
- [ ] `check_in/check_out`: día laboral, turno nocturno, `hours_worked`, contra ≥1 registro legacy.
- [ ] `pytest` con `python3.12` (gotcha Python 3.14 rompe test client). Cobertura gate CI ≥55%.

### F7 — Deploy + validación
- [ ] `manage.py check` + `migrate --check` limpios.
- [ ] Crear collection Rekognition en AWS (`ensure_collection` / command) + correr `index_faces` para poblar caras de los User con foto.
- [ ] Deploy vía `gh workflow run deploy.yml --ref main` + `gh run watch`. Verificar promoción de tráfico (memoria: varios repos no auto-promueven; `update-traffic --to-latest` si aplica).
- [ ] **Smoke / `/qa-prod`**: kiosko público responde GET 200; POST con selfie de prueba → match esperado contra una cara indexada; lista de eventos faciales 200 (staff `qa_claude`, ver memoria `sd_qa_user` — ojo `is_active` estuvo false, verificar).
- [ ] Comentar issue con estados 🟢/🟡/🔵, root del diseño, migraciones aplicadas, URLs smokeadas, registro legacy probado. Asignar `Indunnova` (no cerrar).

## Riesgos / consideraciones
- **Privacidad/biometría**: almacenar selfies + datos biométricos en AWS implica tratamiento de datos sensibles (Habeas Data / Ley 1581 CO). Validar consentimiento y política de retención de `FaceCheckEvent.selfie`.
- **Cross-cloud**: SD vive en GCP; Rekognition en AWS. Latencia extra + 2do proveedor con credenciales. Aislado en `services_rekognition.py` → si mañana se cambia de backend, solo ese archivo.
- **Costo**: ~USD 1 / 1000 `search_faces_by_image`. Kiosko público sin login → posible abuso/spam de llamadas; considerar rate-limit (axes ya está instalado) o token en la URL del QR.
- **Calidad de `User.photo`**: muchas fotos de perfil pueden no ser frontales aptas para indexar. `index_faces` debe reportar cuántas fallan (`NoFaceDetectedError`).
- **Día laboral 22:00**: heredado del turno noche de Logística; confirmar para SD (F0).

## Estimación
F1-F6 desarrollo: ~1.5–2 días. F0 (creds AWS + decisiones) y F7 (deploy + indexado + QA) dependen de disponibilidad de credenciales AWS y de la calidad de las fotos en `User`.
