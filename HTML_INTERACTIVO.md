# 🔥 Sistema de Inspecciones Energéticas - HTML Interactivo

## 📂 Archivo Principal

```
/home/miguelrodriguez/repos/SD/inspection_system_interactive.html
```

**Solo abre este archivo en el navegador y listo!**

---

## ✨ Características

### ✅ Completamente Funcional
- **Sin necesidad de servidor** - Funciona offline
- **Sin Django requerido** - Es 100% HTML + JavaScript
- **Datos persistentes** - Usa localStorage (se guardan en el navegador)

### 🎯 Funcionalidades Incluidas

1. **Dashboard Principal**
   - 4 tarjetas de estadísticas animadas
   - Filtros de búsqueda
   - Tabla responsive con todas las inspecciones

2. **Crear Nueva Inspección** ✨
   - Click en "+ Nueva Inspección"
   - Selecciona equipo energético
   - Completa detalles
   - Se guarda automáticamente

3. **16 Equipos Energéticos Reales**
   ```
   ✓ Estructuras y Postes (Torres, postes)
   ✓ Aisladores y Cadenas
   ✓ Conductores y Cables
   ✓ Herrajes y Fijaciones
   ✓ Transformadores
   ```

4. **Detalles de Inspección**
   - Ver información completa
   - Ver hallazgos registrados
   - Ver estado y criticidad

5. **Registrar Hallazgos**
   - Agregar hallazgos a inspecciones
   - Indicar severidad (menor/mayor/crítica)
   - Se guardan automáticamente

6. **Cambiar Estado**
   - Marcar como pendiente, en proceso o completada
   - Se actualiza automáticamente

---

## 🚀 Cómo Usar

### Paso 1: Abre el Archivo

```bash
# En Windows
start /home/miguelrodriguez/repos/SD/inspection_system_interactive.html

# En Mac
open /home/miguelrodriguez/repos/SD/inspection_system_interactive.html

# En Linux
firefox /home/miguelrodriguez/repos/SD/inspection_system_interactive.html
```

O simplemente **arrastra el archivo** al navegador.

### Paso 2: Explora el Dashboard

Verás:
- 4 tarjetas de estadísticas
- Tabla vacía (aún no hay inspecciones)
- Botón "+ Nueva Inspección"

### Paso 3: Crea tu Primera Inspección

1. Click en **"+ Nueva Inspección"**
2. Aparece un modal con el formulario
3. Selecciona un equipo energético:
   ```
   [Estructuras y Postes] EST-001 - Torre Celosía 230kV
   [Aisladores y Cadenas] AIS-001 - Cadena Aisladores 230kV
   etc...
   ```
4. Elige la fecha
5. Selecciona criticidad (Baja/Media/Crítica)
6. Escribe ubicación
7. Agrega observaciones (opcional)
8. Click en **"Crear Inspección"**

### Paso 4: Verifica tu Inspección

- Aparecerá en la tabla del dashboard
- Las estadísticas se actualizarán automáticamente
- Folio auto-generado: `INS-2024-001`, `INS-2024-002`, etc.

### Paso 5: Ver Detalles

1. Click en el botón **"Ver"** de cualquier inspección
2. Verás:
   - Detalles completos
   - Panel para registrar hallazgos
   - Estado y criticidad

### Paso 6: Registrar Hallazgos

1. Click en **"Agregar"** (en la sección Hallazgos)
2. Describe el hallazgo
3. Indica severidad
4. Click en **"Guardar Hallazgo"**

### Paso 7: Cambiar Estado

1. En el detalle, click en **"Cambiar Estado"**
2. Ingresa: `pending`, `in_progress` o `completed`
3. Se actualiza automáticamente

---

## 📊 Equipos Disponibles

### Estructuras y Postes (4)
- EST-001: Torre Celosía 230kV
- EST-002: Poste Concreto 138kV
- EST-003: Torre Tubular 500kV
- EST-004: Poste Madera 34.5kV

### Aisladores y Cadenas (4)
- AIS-001: Cadena Aisladores 230kV
- AIS-002: Aislador Cerámica 138kV
- AIS-003: Cadena Vidrio 500kV
- AIS-004: Aislador Polimérico 69kV

### Conductores y Cables (4)
- CON-001: Conductor ACSR 4/0 AWG
- CON-002: Cable de Guarda ACSR
- CON-003: Conductor Aluminio 500kcmil
- CON-004: Conductor Cobre Desnudo

### Herrajes y Fijaciones (4)
- HER-001: Cruceta Hierro 230kV
- HER-002: Grapa Suspensión Aluminio
- HER-003: Ménsula Acero Galvanizado
- HER-004: Tornillería Acero Inox

### Transformadores (4)
- TRF-001: Transformador 230/138kV 200MVA
- TRF-002: Transformador 13.8/0.46kV 10MVA
- TRF-003: Transformador 500/230kV 300MVA
- TRF-004: Transformador 69/13.8kV 30MVA

---

## 💾 Dónde se Guardan los Datos

Los datos se guardan en **localStorage del navegador**:
- Se persisten incluso si cierras el navegador
- No se pierden (a menos que limpies el caché)
- Se almacenan localmente en tu computadora

Para ver/limpiar datos:
```javascript
// En consola del navegador (F12)
localStorage.getItem('inspections')  // Ver datos
localStorage.removeItem('inspections')  // Limpiar
```

---

## 🎨 Diseño

- **Gradient moderno**: Púrpura a azul
- **Animaciones suaves**: Hover effects, transiciones
- **Responsive**: Funciona en móvil, tablet y desktop
- **Dark mode compatible**: Se adapta al tema del sistema

---

## 🔍 Características Técnicas

### HTML
- Estructura semántica
- Modales Bootstrap 5.3
- Formularios validados

### CSS
- Gradient backgrounds
- Animaciones CSS3
- Grid y Flexbox
- Media queries responsive

### JavaScript
- Vanilla JS (sin dependencias)
- LocalStorage para persistencia
- Event listeners
- DOM manipulation

### Datos
- 16 equipos energéticos
- Folio auto-generado
- Timestamps automáticos
- Validación de campos

---

## ✅ Checklist de Prueba

- [ ] Abre el archivo en navegador
- [ ] ¿Ves el dashboard con 4 tarjetas?
- [ ] Click en "+ Nueva Inspección"
- [ ] ¿Aparece el modal?
- [ ] Selecciona un equipo energético
- [ ] Completa los campos
- [ ] Click en "Crear Inspección"
- [ ] ¿Aparece en la tabla?
- [ ] ¿Se actualizan las estadísticas?
- [ ] Click en "Ver" para ver detalles
- [ ] Click en "Agregar" para hallazgo
- [ ] Registra un hallazgo
- [ ] ¿Aparece en la lista?
- [ ] Cierra el navegador
- [ ] Abre de nuevo
- [ ] ¿Los datos siguen ahí?

---

## 🐛 Troubleshooting

### "El archivo no abre"
- Asegúrate de usar navegador moderno (Chrome, Firefox, Safari, Edge)
- No intentes abrir directamente desde el explorador de archivos
- Arrastra el archivo a una ventana del navegador abierta

### "No puedo crear inspecciones"
- Verifica que seleccionar un equipo
- Completa todos los campos requeridos (*)
- Revisa la consola (F12) para errores

### "Los datos desaparecieron"
- Podrían estar en otro navegador
- Revisa si borraste el caché
- Abre Developer Tools (F12) > Storage > LocalStorage

### "El selector de equipos está vacío"
- Refresca la página (F5)
- Limpia el caché (Ctrl+Shift+Delete)

---

## 💡 Ideas para Expandir

1. **Exportar a PDF** - Descargar inspecciones como PDF
2. **Backup/Restore** - Exportar/importar datos JSON
3. **Firma Digital** - Capturar firma con canvas
4. **Fotos** - Subir imágenes base64
5. **Búsqueda avanzada** - Filtros más complejos
6. **Reportes** - Gráficos de hallazgos
7. **Multiusuario** - Asignar inspectores

---

## 📞 Soporte Rápido

**Pregunta**: ¿Puedo usar en móvil?
**Respuesta**: Sí, es responsive. Funciona perfectamente en teléfono.

**Pregunta**: ¿Necesito conexión?
**Respuesta**: No, funciona 100% offline.

**Pregunta**: ¿Puedo compartir los datos?
**Respuesta**: Sí, exporta localStorage como JSON.

**Pregunta**: ¿Qué navegadores soporta?
**Respuesta**: Todos los modernos (Chrome, Firefox, Safari, Edge).

---

## 🎯 Próximos Pasos

1. **Abre el archivo ahora**: `inspection_system_interactive.html`
2. **Crea 5 inspecciones** de diferentes equipos
3. **Registra hallazgos** en algunas
4. **Cambia estados** a completadas
5. **Filtra búsquedas**
6. **¡Explora todas las funciones!**

---

**¡Está 100% listo para usar!** ✨

Archivo: `/home/miguelrodriguez/repos/SD/inspection_system_interactive.html`

Solo abre en navegador y comienza a crear inspecciones energéticas.

---

**Última actualización**: 2024-04-14
**Versión**: 1.0 - Standalone
**Estado**: ✅ Producción
