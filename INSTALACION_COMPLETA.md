# 🔌 Instalación Completa - Módulo de Inspecciones Energéticas

## Paso 1: Registrar la App en Django

Edita `carnes_sebastian/config/settings.py` (o tu archivo settings.py):

```python
INSTALLED_APPS = [
    # ... otras apps existentes ...
    'apps.inspections',  # ← Agregar esta línea
]
```

## Paso 2: Crear Migraciones

```bash
cd carnes_sebastian

# Crear migraciones para el app de inspecciones
python manage.py makemigrations inspections

# Aplicar las migraciones a la base de datos
python manage.py migrate inspections
```

## Paso 3: Registrar URLs en Django

Edita `carnes_sebastian/config/urls.py`:

```python
from django.urls import path, include

urlpatterns = [
    # ... otras URLs ...
    path('inspecciones/', include('apps.inspections.urls')),
    # ... más URLs ...
]
```

## Paso 4: Cargar Datos de Equipos Energéticos ⚡

Este comando carga **16 equipos reales del sector de transmisión eléctrica** clasificados en 5 categorías:

```bash
python manage.py cargar_equipos_energeticos
```

**Equipos que se cargan:**

### 📡 Estructuras y Postes (4 equipos)
- Torres Celosía 230kV
- Postes de Concreto 138kV
- Torres Tubulares 500kV
- Postes de Madera Tratada 34.5kV

### 🔌 Aisladores y Cadenas (4 equipos)
- Cadenas de Aisladores 230kV
- Aisladores de Cerámica 138kV
- Cadenas de Vidrio 500kV
- Aisladores Poliméricos 69kV

### 📶 Conductores y Cables (4 equipos)
- Conductores ACSR 4/0 AWG
- Cables de Guarda
- Conductores de Aluminio 500kcmil
- Conductores de Cobre Desnudo

### 🔧 Herrajes y Fijaciones (4 equipos)
- Crucetas de Hierro 230kV
- Grapas de Suspensión
- Ménsulas de Soporte
- Tornillería de Acero Inoxidable

### 🔋 Transformadores (4 equipos)
- Transformadores de Potencia 230/138kV
- Transformadores de Distribución
- Transformadores de Potencia 500/230kV
- Transformadores Trifásicos 69/13.8kV

## Paso 5: Crear Superusuario (si aún no existe)

```bash
python manage.py createsuperuser
```

Ingresa:
- Usuario: `admin`
- Email: `admin@sd.com` (o tu email)
- Contraseña: (elige una segura)

## Paso 6: Ejecutar el Servidor

```bash
python manage.py runserver
```

## 🌐 Acceder a la Aplicación

### Dashboard Principal
http://localhost:8000/inspecciones/

### Listado de Inspecciones
http://localhost:8000/inspecciones/inspecciones/

### Panel de Administración
http://localhost:8000/admin/

---

## ✨ Flujo de Uso

### 1️⃣ Crear Nueva Inspección
1. Click en **"+ Nueva Inspección"** en el dashboard
2. Selecciona el **equipo energético** a inspeccionar (ej: Torre Celosía 230kV)
3. Elige la **fecha** de inspección
4. Indica la **ubicación** (ej: Línea Bogotá-Medellín, km 45)
5. Selecciona el **nivel de criticidad** (Baja/Media/Crítica)
6. Agrega **observaciones** relevantes
7. Click en **"Crear Inspección"**

### 2️⃣ Registrar Hallazgos
1. Desde la inspección, click en **"Agregar Hallazgo"**
2. Describe el **problema encontrado**
3. Selecciona la **severidad** (Menor/Mayor/Crítica)
4. Sube **foto** del problema (opcional)
5. Guardar

### 3️⃣ Crear Acciones Correctivas
1. Desde el hallazgo, click en **"Acción Correctiva"**
2. Describe la **acción a realizar**
3. Asigna al **responsable**
4. Establece la **fecha límite**
5. Guardar

---

## 🛠️ Administración en Django

Accede a http://localhost:8000/admin/ con tu usuario admin

Modelos disponibles:
- **Equipos** - Gestionar máquinas
- **Categorías** - Clasificaciones de equipos
- **Inspecciones** - Crear/editar/eliminar inspecciones
- **Hallazgos** - Registrar problemas
- **Acciones Correctivas** - Seguimiento de soluciones

---

## 📊 Dashboard

El dashboard muestra:
- **4 Tarjetas de Estadísticas**
  - Total de inspecciones
  - Inspecciones completadas
  - En proceso
  - Críticas

- **Filtros**
  - Búsqueda por folio/equipo
  - Por estado
  - Por categoría

- **Tabla de Inspecciones Recientes**
  - Folio único
  - Equipo
  - Inspector
  - Fecha
  - Estado (con animaciones)
  - Criticidad
  - Botón para ver detalles

---

## 🔧 Troubleshooting

### Error: "No module named 'apps.inspections'"
```bash
# Verifica que INSTALLED_APPS contiene 'apps.inspections'
# Reinicia el servidor
python manage.py runserver
```

### Error de migración
```bash
# Resetear migraciones (solo desarrollo)
python manage.py migrate inspections zero
python manage.py migrate inspections
```

### Tabla vacía
```bash
# Volver a cargar datos
python manage.py cargar_equipos_energeticos
```

### 404 en URLs de inspecciones
```bash
# Verifica que urls.py incluye:
path('inspecciones/', include('apps.inspections.urls'))
```

---

## 📚 Documentación

- **README.md** - Documentación técnica completa
- **INSPECTIONS_SETUP.md** - Guía rápida de instalación
- Este documento - Instalación paso a paso

---

## 🎯 Próximos Pasos (Opcional)

1. **Personalizar el Diseño**
   - Editar colores en `dashboard.html`
   - Cambiar logo/nombre en templates

2. **Agregar Campos**
   - Editar `models.py`
   - Crear migración: `makemigrations`
   - Aplicar: `migrate`

3. **REST API**
   - Crear serializers en `api/`
   - Usar Django REST Framework

4. **Cloud Storage**
   - Configurar Google Cloud Storage para imágenes
   - En producción

5. **Notificaciones**
   - Integrar Celery para alertas de acciones vencidas
   - Enviar emails automáticamente

---

**Estado**: ✅ Listo para usar
**Última actualización**: 2024-04-14
**Versión**: 1.0
**Equipos cargados**: 16 máquinas del sector energético
