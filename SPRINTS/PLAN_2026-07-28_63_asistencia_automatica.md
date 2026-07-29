# PLAN — SD#63 (reproceso bounce=3): PDF FT-HSEQ-60 en blanco y negro con logo pequeño

**Fecha:** 2026-07-28
**Issue:** [Indunnova16/SD#63](https://github.com/Indunnova16/SD/issues/63) — `enhancement`, `Urgente`
**Branch:** `fix/sd-63-2026-07-28` (worktree `/Users/miguelrodriguez/SD-wt-63`)
**Watchdog:** `reproceso_rate.py` → **ES UN REPROCESO — 3 rebote(s)**. Post-mortems ya
registrados: `FIX_INCOMPLETO/validado_1_registro` (bounce 1), `FIX_INCOMPLETO/otro`
(bounce 2). Falta el de bounce 3 (este).

---

## 1. Historia del issue — 9 comentarios, 3 rebotes

| # | Fecha | Autor | Qué pasó |
|---|---|---|---|
| body | 07-17 | Indunnova | 4 puntos: (1) PDF al formato oficial FT-HSEQ-60, (2) validar campos antes de generar, (3) asistencia automática por curso sin lección manual, (4) permisos ya OK, documentar |
| C1 | 07-17 | Indunnova | **Adición:** enlace en navbar desktop + móvil, gateado Coordinador + Administrador |
| C2 | 07-20 | mbrt26 | 🟢 Limpieza de 7 lecciones legacy `Lesson.Type.ATTENDANCE` (4 borradas, 2 archivadas, 1 sin tocar) |
| C3 | 07-20 | Indunnova | **REBOTE 1** — "Listo validado / 1 falta aplicar el mismo formato" |
| C4 | 07-22 | Indunnova | Adjunta el DOCX oficial. 5 desviaciones: bandas azules, tipo de actividad como texto plano, columna "Estado" de más, sección "Resumen de Asistencia" que no existe, Eficacia truncada. + filas dinámicas (no 14 fijas) |
| C5 | 07-22 | mbrt26 | 🟢 Validado en prod, 7 entregables ✅. Post-mortem bounce 1 |
| C6 | 07-23 | Indunnova | **REBOTE 2** — validación en vivo (Andrea + Linda), 10 puntos. Nuevos: fecha de firma también en el PDF (p4), 2 tipos de PDF Grupal+Individual (p5). Pendientes declarados por el propio cliente: UX de validación de campos (p6), instructor por sesión (p7 → p10). Aplazado explícito: módulo "Programación de cursos" (p10) |
| C7 | 07-23 | Indunnova | "necesito que los pdf de la asistencia queden con **este mismo formato, colores y logo** y todo porfa" + DOCX de nuevo |
| C8 | 07-27 | mbrt26 | 🟡 Cierre: logo real + acento rojo `#e4020f`, columna "Fecha de firma", PDF Individual nuevo. Post-mortem bounce 2 |
| C9 | 07-28 | Indunnova | **REBOTE 3 ← ALCANCE DE ESTA VUELTA** |

### El pedido REAL de esta vuelta (C9, 2026-07-28)

> "El PDF quedó con branding rojo y logo gigante — **debe ser blanco y negro con logo
> pequeño**. Los campos e información ya están correctos y funcionando […] **eso no
> requiere cambios**."

Fix señalado por el propio cliente, con línea exacta:
- Quitar `{{ brand_accent }}` de `.header h1` (**línea 29**) y `.header` (**línea 19**) →
  negro `#1a1a1a`.
- Reducir `.header-logo` (**líneas 23-26**, hoy `max-height: 42px`) — *"revisar por qué se
  está renderizando tan grande"*.

Las referencias de línea del cliente coinciden **exactamente** con el código actual de
`templates/courses/course_attendance_pdf.html` — está leyendo el mismo archivo.

### Post-mortem de la intervención previa (bounce 3)

- **Qué afirmamos (C8, 07-27):** entregable 1 y 2 ✅ "Logo + acento `#e4020f` en PDF
  Grupal / Legado — *verificado visualmente (pdftoppm) contra prod*".
- **Qué falló realmente — dos cosas independientes:**
  1. **MALENTENDIDO de intención.** C7 decía "que los PDF queden con **este mismo
     formato, colores y logo**" señalando al DOCX adjunto. El antecedente de "este" era
     **el documento oficial**, no la app: el oficial es blanco y negro con un logo de
     membrete. Se leyó como "traé el branding de la app (rojo `#e4020f` de SD#69) al
     PDF", que es lo contrario de la instrucción vigente desde C4 ("blanco y negro,
     quitar las bandas de color"). El propio PLAN de bounce 2 registró esta tensión como
     riesgo ("aparente contradicción") y la resolvió a favor del rojo — sin volver a
     abrir el DOCX para comprobar de qué color es el oficial.
  2. **Verificación visual que no midió.** Se declaró "verificado visualmente con
     pdftoppm", pero un logo que ocupa **524,7 pt de ancho sobre 527 pt útiles** (todo el
     ancho de la página) es imposible de no ver. La inspección visual se hizo sobre el
     *hecho* de que el logo aparecía, no sobre su *tamaño*; nunca se midió el objeto
     renderizado.
- **Por qué no lo atrapamos:** el DOCX oficial estaba adjunto en C4 **y** en C7 **y** en
  C9 — tres veces — y contiene la respuesta a las dos preguntas (qué color, qué tamaño de
  logo). El oracle estuvo disponible todo el tiempo y no se consultó para el punto de
  branding; se consultó solo para la estructura de campos.
- **Corrección esta vez:** se abrió el DOCX (`unzip` + `word/header1.xml`) y se midió el
  membrete oficial en EMU; y el tamaño renderizado se verifica con `pdfimages -list`
  (número medido, no impresión visual).

---

## 2. Causa raíz del "logo gigante" — medida, no inferida

`xhtml2pdf` **no implementa `max-width` / `max-height` sobre `<img>`**. Verificado en el
código del motor (`xhtml2pdf/tags.py`, `class pisaTagIMG`, v0.2.17): solo lee
`c.frag.width` / `c.frag.height` (CSS `width`/`height`) y los atributos HTML
`width`/`height`. `max-*` nunca se consulta → la declaración es **silenciosamente
ignorada** y la imagen se dibuja a tamaño natural (1800×1200 px), recortada solo por el
ancho del frame.

Medición real (`pdfimages -list`, tamaño dibujado = píxeles / ppi × 72):

| CSS en `.header-logo` | Tamaño dibujado | Veredicto |
|---|---|---|
| `max-height: 42px` (**actual en prod**) | **524,7 × 349,8 pt** | ancho útil de página = 527 pt → ocupa el 99,6 % del ancho y el 44 % del alto |
| `height: 42px` | 47,3 × 31,5 pt | respetado |
| `width: 92pt; height: 61pt` | 92,0 × 61,0 pt | respetado |

El mismo defecto afecta a `.signature-img` (`max-height: 36px; max-width: 110px`) en
**ambos** templates: la firma del instructor/responsable, que vive en una celda a ancho
completo, se dibuja a **450 pt de ancho** en el Grupal y **187 pt** en el Legado. Las
firmas del roster se salvan por accidente (la columna las acota a ~87-92 pt).

## 3. Oracle de tamaño y color — del DOCX oficial, no inventado

`FT-HSEQ-60 Lista de asistencia V04 EN BLANCO.docx` → `word/header1.xml`:

- `<wp:extent cx="1171575" cy="857250">` EMU = **1,281 in × 0,938 in = 92,2 pt × 67,5 pt =
  32,5 mm × 23,8 mm**. Ese es el membrete oficial.
- La imagen del membrete (`media/image.png`, 123×90 px) **es el logo SD S.A.S. a color**
  (torre negra + "SD" rojo + "Salomón Durán").

→ Resuelve la aparente contradicción de C9 ("blanco y negro **con logo**"): el documento
oficial es blanco y negro **en texto, líneas y tablas**, y lleva el logo **a color** en un
membrete pequeño. El logo **no** se convierte a escala de grises.

**Tamaño elegido: `width: 90pt; height: 60pt`** — relación de aspecto exacta del asset
(1800/1200 = 1,5 → 90/60 = 1,5, sin deformación) y cabe dentro del recuadro oficial de
92,2 × 67,5 pt. Reducción de 524,7 → 90 pt de ancho (5,8× lineal, 34× en área).

---

## 4. Tabla de entregables (gate anti-FIX_INCOMPLETO)

| # | Entregable | Evidencia obtenida | ✅/❌ |
|---|---|---|---|
| 1 | `.header h1` del Grupal en negro `#1a1a1a`, sin `{{ brand_accent }}` | HTML renderizado: `#e4020f` ausente. Test `test_regresion_sin_rojo_corporativo_bounce_2026_07_28`. Visual: título negro | ✅ |
| 2 | `.header` border-bottom del Grupal en negro | Mismo test + inspección visual: líneas divisorias negras | ✅ |
| 3 | Logo del Grupal a tamaño de membrete | `pdfimages -list`: **524,7 × 349,8 pt → 90,0 × 60,0 pt** | ✅ |
| 4 | Mismo tratamiento en el Legado `attendance_pdf.html` | HTML sin `#e4020f`; `pdfimages`: **524,7 → 90,0 × 60,0 pt**; visual de página 1 | ✅ |
| 5 | PDF Individual hereda el fix | Render con `is_individual=True`: logo **90,0 × 60,0 pt**, sin `#e4020f`, título "Reporte Individual de Asistencia" | ✅ |
| 6 | Logo conserva su color (oracle: el oficial lo trae a color) | Inspección visual del PNG: logo a color, igual que `media/image.png` del DOCX | ✅ |
| 7 | Firma de instructor/responsable a tamaño razonable | `pdfimages`: Grupal **450,0 → 82,4 pt**; Legado **187,0 → 82,4 pt**; roster 86,7 → 82,4 pt | ✅ |
| 8 | Sin regresión de contenido | Suite verde + visual: campos, casillas (X en Capacitación), 6 columnas, Eficacia completa, todo en página 1 | ✅ |
| 9 | Sin regresión de bounce 2 | `test_regresion_sigue_sin_banda_azul` y `test_regresion_sin_azul_bounce_2` verdes; `#2563eb` ausente | ✅ |
| 10 | Test de regresión anti-`#e4020f` en los 2 templates | 2 tests nuevos de regresión (Grupal + Legado) + 2 de tamaño explícito del logo | ✅ |
| 11 | `_attendance_pdf_branding_context()` deja de exponer `brand_accent` | `test_regresion_no_expone_color_de_marca`: `set(context) == {"logo_data_uri"}` | ✅ |
| 12 | Suite completa verde | **1456 passed, 1 skipped, 0 failed** (baseline 1454+1; +2 tests nuevos). Ruff idéntico a HEAD | ✅ |

### Medición final (`pdfimages -list`, tamaño dibujado en pt)

| Objeto | Antes | Después |
|---|---|---|
| Logo, Grupal | 524,7 × 349,8 | **90,0 × 60,0** |
| Logo, Legado | 524,7 × 349,8 | **90,0 × 60,0** |
| Logo, Individual | (heredaba el mismo defecto) | **90,0 × 60,0** |
| Firma instructor (celda ancho completo, Grupal) | 450,0 × 150,0 | **82,4 × 27,5** |
| Firma responsable (Legado) | 187,0 × 62,3 | **82,4 × 27,5** |
| Firmas del roster | 86,7 × 28,9 | **82,4 × 27,5** |

Efecto colateral favorable: al dejar de consumir 350 pt de alto, el formato completo
(datos + casillas + firmantes + Eficacia) vuelve a caber en **una sola página**; antes el
roster se desbordaba a la página 2.

### Fuera de alcance (declarado, no adivinado)

| Punto | Origen | Razón |
|---|---|---|
| UX de validación de campos antes del PDF | body p2 / C6 p6 | El propio cliente: *"sigue pendiente definir"*. Indefinición genuina de producto |
| Instructor por sesión | C6 p7 | El cliente lo difiere a C6 p10 |
| Módulo "Programación de cursos" | C6 p10 | *"queda explícitamente para analizar más adelante — no implementar todavía"* |
| Branding `#e4020f` del resto de la app (navbar, botones, certificados, `user_profile_pdf.html`) | SD#69 | C9: *"El branding rojo del #69 aplica a la interfaz general de la app, **no** a este documento"*. **NO se toca** |

---

## 5. Archivos a tocar

- `templates/courses/course_attendance_pdf.html` — `.header`, `.header h1`,
  `.header-logo`, `.signature-img`
- `templates/courses/attendance_pdf.html` — `.header`, `.header .brand-logo`,
  `.signature-img`
- `apps/courses/views.py` — `_attendance_pdf_branding_context()` deja de devolver
  `brand_accent`
- `apps/courses/tests/test_issue_63.py` — invertir las 2 aserciones de "acento presente" a
  aserciones de regresión "acento ausente"; quitar `brand_accent` de los 2 helpers de
  contexto y de los 2 tests del helper; test nuevo de tamaño explícito del logo

**Migraciones: NINGUNA.** No se toca ningún modelo — el cambio es CSS de plantilla más un
`dict` de contexto. Cero riesgo sobre datos productivos.

**Data fix en prod: NO requiere.** Nada que backfillear.
