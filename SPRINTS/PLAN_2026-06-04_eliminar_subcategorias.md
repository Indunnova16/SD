# PLAN — Eliminar subcategorías, dejar solo Categorías (issue #34)

**Fecha:** 2026-06-04
**Issue:** [Indunnova16/SD#34](https://github.com/Indunnova16/SD/issues/34)
**Estado:** Planning completado, listo para ejecución
**Bundle:** RUN_2026-06-04_0002 — UN solo deploy con #34 + #35 + #36. #35 NO crea migración. La migración de #34 es **0018** (último número actual: 0017_lesson_scheduled_date).

## Contexto

El modelo `Category` (apps/courses/models.py, `db_table=course_categories`) implementa
"subcategorías" mediante una FK self-referential `parent` (`on_delete=CASCADE`,
`related_name="children"`). El issue pide eliminar el concepto de subcategoría y dejar
un único nivel de Categorías (modelo flat).

**Estado prod (confirmado F1):** 7 categorías = 3 padre + 4 sub. **0 cursos** apuntan a
las 4 subcategorías. El campo `parent` se puede eliminar sin pérdida de datos de cursos.

### Decisión de datos en la migración (documentada)

Las 4 filas subcategoría (`parent IS NOT NULL`) tienen 0 cursos asociados. Al eliminar el
campo `parent` quedarían como categorías top-level "fantasma" sin contexto. **Decisión: la
migración 0018 elimina (DELETE) las filas con `parent IS NOT NULL` ANTES de remover el
campo**, vía `RunPython` con reverse no-op. Es lo más simple y seguro: no hay cursos
huérfanos posibles (0 referencias), y evita dejar basura en el maestro de Categorías.
Si en algún entorno (staging) una subcategoría tuviera cursos, el `RunPython` debe
re-parentear esos cursos a la categoría padre antes de borrar — pero en PROD no aplica
(0 cursos). El forward de RunPython debe ser defensivo: re-asignar `course.category` al
`parent` si existen cursos, luego borrar las subcategorías, luego `RemoveField(parent)`.

## Sub-items (versión 1.0 completa — un solo sprint, deploy bundle)

| # | Sub-item | Archivos | Tests | Dependencias | Estado |
|---|---|---|---|---|---|
| A1 | Migración 0018: re-parentear cursos (defensivo) + DELETE subcategorías + RemoveField(parent) | apps/courses/migrations/0018_remove_category_parent.py | migrate SQLite CI + smoke prod | - | ⏳ |
| A2 | Modelo Category: remover campo `parent`; simplificar `__str__` (quitar rama `self.parent`) y `full_path` (return self.name) | apps/courses/models.py | test_models.py | A1 | ⏳ |
| A3 | CategoryForm: remover field `subcategories_text`, método `_save_subcategories`, pre-populate children en `__init__`, llamada en `save()`, y quitar `parent__isnull=True` del `clean_name` (línea ~51) | apps/courses/forms.py | test_forms / test_models | A2 | ⏳ |
| A4 | views.course_list: quitar `subcategory_slug`, ramas `Q(category__parent__slug=...)`, query `subcategories`, y `parent__isnull=True` del filtro de `categories`; quitar context `subcategories`/`current_subcategory`. views.category_delete: quitar guardia "tiene subcategorías" (línea ~604) | apps/courses/views.py | test_views | A2 | ⏳ |
| A5 | reports/views.py: eliminar vista `dashboard_subcategories`; en `_apply_category_filter` y bloque assessments (línea ~457) renombrar/simplificar el filtro `subcategory` para que use solo `category` (no romper dashboard de reportes) | apps/reports/views.py | test_reports si existe | A2 | ⏳ |
| A6 | reports/urls.py: remover ruta `dashboard/subcategories/` (name `dashboard-subcategories`) | apps/reports/urls.py | django check (no reverse roto) | A5 | ⏳ |
| A7 | Template filter_bar.html: remover bloque select "Subcategoría" + hx-get a dashboard-subcategories + target #subcategory-select | templates/dashboard/partials/filter_bar.html | smoke render | A5,A6 | ⏳ |
| A8 | Eliminar template subcategory_options.html | templates/dashboard/partials/subcategory_options.html | - | A5 | ⏳ |
| A9 | Template course_list.html: remover sección "Subcategories" del sidebar (líneas ~53-72) + quitar `[name='subcategory']` de los hx-include | templates/courses/course_list.html | qa-prod journey | A4 | ⏳ |
| A10 | Template category_list.html: remover columna `<th>Subcategorías</th>`, celda children, bloque "Subcategories" (filas hijas), ajustar texto descripción ("categorías y subcategorías"→"categorías") | templates/courses/category_list.html | qa-prod journey | A2 | ⏳ |
| A11 | Template category_form.html: remover bloque "Subcategories asignadas" (`form.subcategories_text`) | templates/courses/category_form.html | qa-prod journey | A3 | ⏳ |
| A12 | API serializers.py: remover `parent`, `children` (SerializerMethodField) y `get_children` de CategorySerializer/CategoryListSerializer | apps/courses/api/serializers.py | test_api.py | A2 | ⏳ |
| A13 | admin.py: verificar y quitar cualquier ref a `parent`/`children` (F1: grep sin hits — confirmar no-op, no inventar cambios) | apps/courses/admin.py | django check | A2 | ⏳ |
| A14 | help/admin_manual.html: quitar menciones a subcategorías si existen (revisar grep antes de tocar) | templates/help/admin_manual.html | render | - | ⏳ |
| A15 | Tests: remover SubCategoryFactory / test_subcategory_*, ajustar factories.py, test_models.py, test_api.py para Category flat; agregar test que confirme que `parent` ya no existe y que crear categoría no acepta subcategories_text | apps/courses/tests/ | pytest verde | A2,A3,A12 | ⏳ |
| A16 | Smoke E2E qa-prod (journey SD_34): /courses/ + /courses/categories/ + /courses/categories/create/ HTTP 200 SIN UI de subcategoría | journeys/SD_34.yaml | Playwright Chromium | A4,A9,A10,A11 | ⏳ |

## DAG dependencias

```
A1 → A2
A2 → A3, A4, A5, A10, A12, A13, A15
A3 → A11, A15
A4 → A9, A16
A5 → A6, A7, A8
A6 → A7
A12 → A15
A9,A10,A11 → A16
```

A1 (migración) primero; A2 (modelo) es el cuello de botella del que dependen casi todos.
A14 independiente (solo doc). Backend (A2-A6,A12,A13) antes que templates (A7-A11) antes que tests/smoke.

## Riesgos y mitigaciones

- **R1 — `parent__isnull=True` en filtro de categorías:** course_list filtra
  `categories = Category.objects.filter(is_active=True, parent__isnull=True)`. Tras
  RemoveField, esa cláusula rompe (`FieldError`). A4 DEBE quitar `parent__isnull=True`.
  Mit: grep `parent` en todo apps/ antes de migrar; CI `manage check` + migrate SQLite.
- **R2 — `reverse_code` migración:** RunPython con reverse no-op; documentar que el
  borrado de subcategorías NO es reversible (aceptable: 0 datos de valor).
- **R3 — colisión número migración (bundle):** confirmado #35 NO crea migración. Número
  0018 libre. Verificar en F3 que ninguna otra rama del bundle creó 0018 antes de mergear.
- **R4 — reports dashboard_subcategories referenciado en JS/HTMX fuera de filter_bar:**
  grep `dashboard-subcategories` / `subcategory` en templates/ y static/ antes de borrar
  la ruta (A6) para no dejar `NoReverseMatch`.
- **R5 — `current_subcategory` / `subcategories` aún referenciados en templates:** tras
  quitar del context, asegurar que ningún template los use (course_list.html los usa →
  A9). Grep `current_subcategory` global.

## Validación esperada (qa_claude smoke + journey)

- `/courses/` → 200, contiene "Catálogo de Cursos" y NO contiene el label de sidebar
  ">Subcategorías<" ni el hx-include `[name='subcategory']`.
- `/courses/categories/` → 200, contiene "Gestión de Categorías" y NO contiene
  `<th>Subcategorías</th>`.
- `/courses/categories/create/` → 200, contiene "Crear Categoría" y NO contiene
  "Subcategorías asignadas".
- Crawl maestros adicional (F5): lista cursos, lista categorías, form nueva categoría.
- pytest verde (sin tests de subcategoría), `manage check` + migrate SQLite OK.
