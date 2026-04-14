# Guía Rápida: Integración del Módulo de Inspecciones

## Resumen

Se ha creado un módulo completo de inspecciones para el SD LMS con:
- **Modelos Django** para gestión de inspecciones, equipos, hallazgos y acciones correctivas
- **Vistas y URLs** para CRUD completo
- **Dashboard moderno e interactivo** con estadísticas en tiempo real
- **Formularios** con validación
- **Admin Django** totalmente integrado
- **Servicios** para lógica de negocio
- **Tests** unitarios
- **Documentación completa**

## Pasos de Instalación

### 1. **Registrar en Django Settings**

Edita `carnes_sebastian/config/settings.py`:

```python
INSTALLED_APPS = [
    # ... apps existentes ...
    'apps.inspections',  # ← Agregar esta línea
]
```

### 2. **Crear Migraciones e Inicializar BD**

```bash
cd carnes_sebastian

# Crear migraciones
python manage.py makemigrations inspections

# Aplicar migraciones
python manage.py migrate inspections
```

### 3. **Registrar URLs**

Edita `carnes_sebastian/config/urls.py`:

```python
urlpatterns = [
    # ... urls existentes ...
    path('inspecciones/', include('apps.inspections.urls')),
]
```

### 4. **Crear Datos de Prueba (Opcional)**

```bash
python manage.py shell
```

Dentro del shell:

```python
from apps.inspections.models import EquipmentCategory, Equipment
from datetime import date

# Crear categorías
cat_exc = EquipmentCategory.objects.create(
    name='Excavadoras',
    description='Máquinas excavadoras de construcción'
)

cat_gra = EquipmentCategory.objects.create(
    name='Grúas',
    description='Grúas y equipos de levantamiento'
)

# Crear equipos
Equipment.objects.create(
    folio='EXC-001',
    name='Excavadora CAT 320',
    category=cat_exc,
    location='Planta Principal',
    acquisition_date=date(2020, 1, 15),
    serial_number='CAT320-2020-001'
)

Equipment.objects.create(
    folio='GRA-001',
    name='Grúa Móvil 25 toneladas',
    category=cat_gra,
    location='Patio de Maniobras',
    acquisition_date=date(2019, 5, 20),
    serial_number='GRUM25-2019-001'
)

print("✓ Datos de prueba creados")
exit()
```

### 5. **Crear Superusuario (si no existe)**

```bash
python manage.py createsuperuser
```

### 6. **Ejecutar Servidor**

```bash
python manage.py runserver
```

## URLs Disponibles

Después de registrar las URLs, tendrás acceso a:

| URL | Descripción |
|-----|-------------|
| `/inspecciones/` | Dashboard principal |
| `/inspecciones/inspecciones/` | Listado de inspecciones |
| `/inspecciones/inspecciones/nueva/` | Crear nueva inspección |
| `/inspecciones/inspecciones/<id>/` | Ver detalle de inspección |
| `/inspecciones/equipos/` | Listado de equipos |
| `/admin/` | Panel de administración Django |

## Acceso Admin

Dirección: http://localhost:8000/admin/

Modelos disponibles:
- **Inspecciones** - Gestión completa de inspecciones
- **Equipos** - Catálogo de máquinas
- **Categorías de Equipos** - Clasificación
- **Hallazgos** - Problemas encontrados
- **Acciones Correctivas** - Seguimiento de soluciones
- **Checklists** - Ítems de verificación

## Estructura de Carpetas

```
apps/inspections/
├── __init__.py
├── admin.py                 # Configuración Admin
├── apps.py                  # Configuración de app
├── forms.py                 # Formularios Django
├── models.py                # Modelos de datos
├── services.py              # Lógica de negocio
├── urls.py                  # URLs y rutas
├── views.py                 # Vistas (CBV y FBV)
├── README.md                # Documentación detallada
├── migrations/
│   └── __init__.py
├── templates/inspections/
│   ├── dashboard.html       # Dashboard principal
│   ├── inspection_list.html # Listado
│   ├── inspection_detail.html # Detalle
│   └── inspection_form.html # Formulario
├── api/
│   └── __init__.py          # Para APIs REST futuras
└── tests/
    ├── __init__.py
    └── test_models.py       # Tests unitarios
```

## Próximos Pasos Opcionales

### Implementar REST API
Crear serializers y viewsets en `api/` usando Django REST Framework.

### Agregar Más Campos
Editar `models.py` para agregar campos específicos del negocio.

### Personalizar Plantillas
Las plantillas en `templates/inspections/` heredan de `base.html` y pueden personalizarse.

### Configurar Almacenamiento de Imágenes
Para producción, configurar Google Cloud Storage en lugar de archivos locales.

## Troubleshooting

### Error: "No se encuentra 'inspections' app"
- Verifica que INSTALLED_APPS contiene `'apps.inspections'`
- Reinicia el servidor

### Error en migraciones
```bash
python manage.py migrate --run-syncdb
```

### Tabla no existe
```bash
python manage.py migrate inspections
```

### Limpiar migraciones (desarrollo)
```bash
python manage.py migrate inspections zero
python manage.py migrate inspections
```

## Contacto y Soporte

Documentación completa en: `apps/inspections/README.md`

---

**Estado**: ✅ Listo para integración
**Última actualización**: 2024-04-14
**Versión**: 1.0
