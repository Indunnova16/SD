# Módulo de Inspecciones - SD LMS

Sistema integral de gestión de inspecciones de equipos y maquinaria para SD S.A.S.

## Descripción

El módulo de inspecciones permite:
- **Crear inspecciones** de máquinas y equipos
- **Registrar hallazgos** con fotos y descripciones
- **Generar acciones correctivas** para resolver problemas
- **Capturar firmas digitales** de inspectores
- **Filtrar y buscar** inspecciones por múltiples criterios
- **Visualizar estadísticas** en un dashboard interactivo

## Instalación

### 1. Registrar la aplicación en Django

Edita `carnes_sebastian/config/settings.py` (o la ubicación de tu settings.py):

```python
INSTALLED_APPS = [
    # ... otras apps
    'apps.inspections',
]
```

### 2. Crear las migraciones

```bash
python manage.py makemigrations inspections
python manage.py migrate inspections
```

### 3. Registrar las URLs

Edita `carnes_sebastian/config/urls.py`:

```python
from django.urls import path, include

urlpatterns = [
    # ... otras URLs
    path('inspecciones/', include('apps.inspections.urls')),
]
```

### 4. Crear datos iniciales (opcional)

```bash
python manage.py shell

# Dentro del shell:
from apps.inspections.models import EquipmentCategory, Equipment
from django.contrib.auth.models import User

# Crear categorías
cat1 = EquipmentCategory.objects.create(
    name='Excavadoras',
    description='Máquinas excavadoras'
)

cat2 = EquipmentCategory.objects.create(
    name='Grúas',
    description='Grúas y polipastos'
)

# Crear equipos
Equipment.objects.create(
    folio='EXC-001',
    name='Excavadora CAT 320',
    category=cat1,
    location='Planta Principal',
    acquisition_date='2020-01-15',
    serial_number='CAT320-2020-001'
)

Equipment.objects.create(
    folio='GRA-001',
    name='Grúa Móvil 25 toneladas',
    category=cat2,
    location='Patio de Maniobras',
    acquisition_date='2019-05-20',
    serial_number='GRUM-25-2019'
)

exit()
```

## Estructura de Modelos

### EquipmentCategory
Categoría del equipo (Excavadoras, Grúas, etc.)

```python
class EquipmentCategory(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
```

### Equipment
Máquinas y equipos a inspeccionar

```python
class Equipment(models.Model):
    folio = models.CharField(max_length=50)
    name = models.CharField(max_length=200)
    category = ForeignKey(EquipmentCategory)
    location = models.CharField(max_length=200)
    acquisition_date = models.DateField()
    serial_number = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
```

### Inspection
Registro de inspección de un equipo

```python
class Inspection(models.Model):
    STATUS_CHOICES = ('pending', 'in_progress', 'completed', 'rejected')
    CRITICALITY_CHOICES = ('low', 'medium', 'critical')

    folio = models.CharField(max_length=50)
    equipment = ForeignKey(Equipment)
    inspector = ForeignKey(User)
    inspection_date = models.DateTimeField()
    status = models.CharField(choices=STATUS_CHOICES)
    criticality = models.CharField(choices=CRITICALITY_CHOICES)
    observations = models.TextField()
    signature_image = models.ImageField()
```

### InspectionChecklist
Checklist de verificación para la inspección

```python
class InspectionChecklist(models.Model):
    inspection = OneToOneField(Inspection)
    operational_condition = models.BooleanField()
    safety_devices_ok = models.BooleanField()
    maintenance_current = models.BooleanField()
    documentation_complete = models.BooleanField()
```

### Finding
Hallazgos encontrados durante la inspección

```python
class Finding(models.Model):
    SEVERITY_CHOICES = ('minor', 'major', 'critical')

    inspection = ForeignKey(Inspection)
    description = models.TextField()
    severity = models.CharField(choices=SEVERITY_CHOICES)
    photo = models.ImageField()
```

### CorrectiveAction
Acciones correctivas para resolver hallazgos

```python
class CorrectiveAction(models.Model):
    STATUS_CHOICES = ('pending', 'in_progress', 'completed', 'cancelled')

    finding = ForeignKey(Finding)
    description = models.TextField()
    responsible = ForeignKey(User)
    due_date = models.DateField()
    status = models.CharField(choices=STATUS_CHOICES)
    completion_date = models.DateField()
```

## URLs Disponibles

| URL | Vista | Descripción |
|-----|-------|-------------|
| `/inspecciones/` | dashboard | Dashboard principal con estadísticas |
| `/inspecciones/inspecciones/` | InspectionListView | Listado de inspecciones |
| `/inspecciones/inspecciones/nueva/` | InspectionCreateView | Crear nueva inspección |
| `/inspecciones/inspecciones/<id>/` | InspectionDetailView | Detalle de inspección |
| `/inspecciones/equipos/` | EquipmentListView | Listado de equipos |
| `/inspecciones/inspecciones/<id>/hallazgo/nuevo/` | FindingCreateView | Agregar hallazgo |
| `/inspecciones/hallazgos/<id>/accion-correctiva/nueva/` | CorrectiveActionCreateView | Crear acción correctiva |

## Vistas (Views)

### dashboard
Dashboard interactivo con:
- Estadísticas (total, completadas, en proceso, críticas)
- Últimas inspecciones
- Filtros por búsqueda y estado
- Inspecciones agrupadas por semana

### InspectionListView
Listado paginado de inspecciones con:
- Búsqueda por folio/equipo/inspector
- Filtro por estado
- Filtro por categoría de equipo
- Tabla con información completa

### InspectionDetailView
Detalle completo de una inspección:
- Información general
- Checklist
- Hallazgos y acciones correctivas
- Panel de estado y criticidad
- Información de auditoría

## Admin Django

El módulo registra todos los modelos en Django Admin:

```bash
python manage.py runserver
# Ir a http://localhost:8000/admin/
```

Acceso:
- Dashboard: Listado de inspecciones
- Equipos: Gestión de máquinas
- Hallazgos: Registros de problemas encontrados
- Acciones Correctivas: Seguimiento de soluciones

## Formularios (Forms)

### InspectionForm
Para crear/editar inspecciones

Campos:
- Equipment (Seleccionar equipo)
- Scheduled Date (Fecha programada)
- Location (Ubicación)
- Observations (Observaciones)
- Criticality (Nivel de criticidad)

### FindingForm
Para registrar hallazgos

Campos:
- Description (Descripción)
- Severity (Severidad: menor, mayor, crítica)
- Photo (Foto del hallazgo)

### CorrectiveActionForm
Para acciones correctivas

Campos:
- Description (Descripción)
- Responsible (Responsable)
- Due Date (Fecha límite)
- Notes (Notas adicionales)

## Características del Dashboard

### Estadísticas
- Total de inspecciones
- Inspecciones completadas
- En proceso
- Críticas

### Filtros
- Búsqueda por folio/equipo
- Por estado (pendiente, en proceso, completada)
- Por categoría de equipo

### Tabla de Inspecciones
- Folio único
- Equipo inspeccionado
- Inspector responsable
- Fecha y hora
- Estado con indicador visual
- Nivel de criticidad
- Botón para ver detalles

### Diseño
- Gradient moderno (púrpura/azul)
- Animaciones suaves
- Responsive (móvil y desktop)
- Iconografía con Font Awesome

## Permisos

Por defecto, el módulo requiere:
- `login_required` para acceder a cualquier vista
- Recomendado: Crear grupo `Inspectores` con permisos específicos

```python
# En Django Admin
# Crear grupo Inspectores
# Otorgar permisos:
# - inspections.add_inspection
# - inspections.change_inspection
# - inspections.view_inspection
# - inspections.delete_inspection
# - inspections.add_finding
# - inspections.add_corrective_action
```

## Almacenamiento de Archivos

Para imágenes (firmas y fotos de hallazgos):
- Configurar en `settings.py`: `MEDIA_ROOT` y `MEDIA_URL`
- En desarrollo: Se guardan en `media/`
- En producción: Usar Google Cloud Storage o similar

```python
# settings.py
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')
```

## Integración con Sistema Existente

El módulo está diseñado para integrarse sin afectar otras apps:
- No depende de otras apps del proyecto
- Usa solo modelos propios
- Compatible con la estructura Django existente
- Requiere usuario autenticado (sistema de autenticación estándar)

## Notas de Desarrollo

- Seguir las convenciones del proyecto (PascalCase para modelos, snake_case para URLs)
- Añadir tests en `tests/`
- Documentar nuevas funcionalidades
- Usar templates que extienden `base.html` del proyecto
- Mantener estilos consistentes con el proyecto

## Próximas Mejoras

- [ ] Exportar inspecciones a PDF
- [ ] Generador de reportes avanzado
- [ ] Integración con CCTV/IoT
- [ ] Notificaciones automáticas para acciones vencidas
- [ ] API REST para aplicaciones móviles
- [ ] Historial completo de inspecciones por equipo
- [ ] Gráficos de tendencias y análisis
