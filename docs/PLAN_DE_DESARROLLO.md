# Plan de Desarrollo - Sistema LMS S.D. S.A.S.

## Sistema de Gestión de Capacitaciones y Plan de Formación

**Versión:** 2.0
**Fecha:** Enero 2026
**Proyecto:** LMS para gestión de competencias en trabajo de alto riesgo
**Alineación:** Estándar Indunnova SAS v2.0

---

## 1. Resumen Ejecutivo

Este documento presenta el plan de desarrollo para el Sistema LMS de S.D. S.A.S., una plataforma integral de gestión del aprendizaje diseñada para garantizar que el personal que opera en líneas de transmisión eléctrica cuente con las competencias necesarias para ejecutar trabajos de alto riesgo de manera segura.

### 1.1 Alcance del Proyecto

| Componente | Descripción |
|------------|-------------|
| **Web App** | Aplicación web responsive con Django + HTMX + Alpine.js |
| **App Móvil** | Aplicaciones nativas Android/iOS con soporte offline completo |
| **Backend API** | API REST/GraphQL con Django + DRF + Django Ninja |
| **CMS** | Sistema de gestión de contenido educativo (LCMS) |
| **Analytics** | Dashboard de reportes y analítica con ECharts |

---

## 2. Stack Tecnológico (Alineado con Indunnova v2.0)

### 2.1 Backend

| Tecnología | Versión | Justificación |
|------------|---------|---------------|
| **Python** | 3.12.x | Mejoras de rendimiento 10-15%, mejor manejo de errores |
| **Django** | 5.1.x LTS | Soporte async nativo mejorado, nuevos campos de modelo |
| **PostgreSQL** | 16.x | Paralelismo mejorado, compresión de datos |
| **Redis** | 7.x | Cache, sesiones, broker Celery |
| **Celery** | 5.3+ | Tareas asíncronas y background jobs |

### 2.2 APIs y Servicios

| Tecnología | Propósito |
|------------|-----------|
| **Django REST Framework 3.15+** | APIs REST principales |
| **Django Ninja** | APIs de alto rendimiento con validación Pydantic |
| **GraphQL (Strawberry)** | Consultas flexibles para dashboards (Fase 2) |
| **drf-spectacular** | Documentación OpenAPI automática |

### 2.3 Frontend Web

| Tecnología | Justificación |
|------------|---------------|
| **HTMX 2.x** | Interactividad SPA-like manteniendo templates Django |
| **Alpine.js 3.x** | Reactividad ligera (15KB) para componentes interactivos |
| **Tailwind CSS 3.x** | Diseño utility-first, mayor flexibilidad |
| **daisyUI** | Componentes prediseñados sobre Tailwind |
| **Hyperscript** | Scripting declarativo para interacciones complejas |
| **Vite** | Build rápido, HMR en desarrollo |

### 2.4 Visualización de Datos

| Librería | Uso |
|----------|-----|
| **Apache ECharts** | Dashboards complejos, mapas, gráficos avanzados |
| **Chart.js 4.x** | Gráficos simples y rápidos |
| **AG Grid Community** | Tablas avanzadas con filtros, ordenamiento, exportación |

### 2.5 Aplicación Móvil

| Tecnología | Justificación |
|------------|---------------|
| **React Native** | Código compartido Android/iOS, ecosistema maduro |
| **Expo** | Desarrollo acelerado, OTA updates, build service |
| **WatermelonDB** | Base de datos offline-first de alto rendimiento |
| **React Native MMKV** | Almacenamiento local ultrarrápido |
| **React Native Background Fetch** | Sincronización en segundo plano |
| **Notifee** | Notificaciones push avanzadas |

### 2.6 Infraestructura (GCP)

| Tecnología | Justificación |
|------------|---------------|
| **Google Cloud Platform** | Región São Paulo, precios competitivos LATAM |
| **Cloud Run** | Contenedores serverless, escalado automático |
| **Cloud SQL** | PostgreSQL 16 gestionado con alta disponibilidad |
| **Memorystore** | Redis 7 gestionado |
| **Cloud Storage** | Almacenamiento de objetos para multimedia |
| **Cloud CDN** | Distribución de contenido multimedia |
| **Cloud Build** | CI/CD automatizado |
| **Terraform** | Infraestructura como código |

### 2.7 Seguridad (Alineado con Indunnova)

| Librería | Propósito |
|----------|-----------|
| **django-axes** | Protección contra fuerza bruta |
| **django-csp** | Content Security Policy headers |
| **django-cors-headers** | CORS configurado correctamente |
| **django-otp** | Autenticación de dos factores (2FA) |
| **python-decouple** | Variables de entorno seguras |
| **GCP Secret Manager** | Gestión de secretos en producción |

### 2.8 Testing y Calidad de Código

| Herramienta | Propósito |
|-------------|-----------|
| **pytest-django** | Testing framework principal |
| **factory_boy** | Factories para fixtures |
| **faker** | Datos de prueba realistas |
| **pytest-cov** | Cobertura de código (>80%) |
| **playwright** | E2E testing |
| **Ruff** | Linter + formatter ultrarrápido |
| **mypy** | Type checking estático |
| **pre-commit** | Hooks de Git para calidad |
| **djLint** | Linting de templates Django |

---

## 3. Arquitectura del Sistema

### 3.1 Diagrama de Alto Nivel

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENTES                                        │
├─────────────────┬─────────────────┬─────────────────┬───────────────────────┤
│   Web App       │   Android App   │    iOS App      │   Portal Auditor ISA  │
│ (Django+HTMX)   │  (React Native) │ (React Native)  │   (Django+HTMX)       │
└────────┬────────┴────────┬────────┴────────┬────────┴───────────┬───────────┘
         │                 │                 │                     │
         └─────────────────┴────────┬────────┴─────────────────────┘
                                    │
                           ┌────────▼────────┐
                           │   Cloud CDN     │
                           │   + Cloud LB    │
                           └────────┬────────┘
                                    │
                           ┌────────▼────────┐
                           │   Cloud Armor   │
                           │     (WAF)       │
                           └────────┬────────┘
                                    │
         ┌──────────────────────────┼──────────────────────────┐
         │                          │                          │
┌────────▼────────┐       ┌────────▼────────┐       ┌────────▼────────┐
│   Django Web    │       │   Django API    │       │   Django Admin  │
│   (Cloud Run)   │       │   (Cloud Run)   │       │   (Cloud Run)   │
│                 │       │                 │       │                 │
│  HTMX + Alpine  │       │  DRF + Ninja    │       │  Django Admin   │
└────────┬────────┘       └────────┬────────┘       └────────┬────────┘
         │                         │                          │
         └─────────────────────────┼──────────────────────────┘
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         │                         │                         │
┌────────▼────────┐      ┌────────▼────────┐      ┌─────────▼───────┐
│  Cloud SQL      │      │  Memorystore    │      │  Cloud Storage  │
│  PostgreSQL 16  │      │  Redis 7.x      │      │  (Media/Files)  │
└─────────────────┘      └─────────────────┘      └─────────────────┘
                                   │
                          ┌────────▼────────┐
                          │  Celery Workers │
                          │ (Cloud Run Jobs)│
                          └─────────────────┘
```

### 3.2 Arquitectura Django (Patrones Indunnova)

```
┌─────────────────────────────────────────────────────────────┐
│              ARQUITECTURA DJANGO - CLEAN ARCHITECTURE        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                    PRESENTATION LAYER                 │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐  │   │
│  │  │   Views     │  │  Templates  │  │  Serializers │  │   │
│  │  │  (Django)   │  │ (HTMX/Alpine│  │   (DRF)      │  │   │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬───────┘  │   │
│  └─────────┼────────────────┼────────────────┼──────────┘   │
│            │                │                │               │
│  ┌─────────▼────────────────▼────────────────▼──────────┐   │
│  │                    SERVICE LAYER                      │   │
│  │  ┌─────────────────────────────────────────────────┐ │   │
│  │  │  apps/*/services.py                             │ │   │
│  │  │  - Business logic                               │ │   │
│  │  │  - Orchestration                                │ │   │
│  │  │  - Transaction management                       │ │   │
│  │  └─────────────────────┬───────────────────────────┘ │   │
│  └────────────────────────┼─────────────────────────────┘   │
│                           │                                  │
│  ┌────────────────────────▼─────────────────────────────┐   │
│  │                  REPOSITORY LAYER                     │   │
│  │  ┌─────────────────────────────────────────────────┐ │   │
│  │  │  apps/*/repositories.py                         │ │   │
│  │  │  - Data access abstraction                      │ │   │
│  │  │  - Query optimization                           │ │   │
│  │  │  - Caching logic                                │ │   │
│  │  └─────────────────────┬───────────────────────────┘ │   │
│  └────────────────────────┼─────────────────────────────┘   │
│                           │                                  │
│  ┌────────────────────────▼─────────────────────────────┐   │
│  │                    DOMAIN LAYER                       │   │
│  │  ┌─────────────────────────────────────────────────┐ │   │
│  │  │  apps/*/models.py                               │ │   │
│  │  │  - Django models                                │ │   │
│  │  │  - Domain entities                              │ │   │
│  │  │  - Validators                                   │ │   │
│  │  └─────────────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 Aplicaciones Django

| Aplicación | Responsabilidad |
|------------|-----------------|
| **accounts** | Autenticación, usuarios, roles, permisos |
| **courses** | Gestión de cursos, módulos, contenido |
| **learning_paths** | Rutas de aprendizaje, prerrequisitos |
| **assessments** | Evaluaciones, banco de preguntas, calificación |
| **certifications** | Certificados, vencimientos, validación QR |
| **lessons_learned** | Lecciones aprendidas, micro-learning |
| **preop_talks** | Charlas pre-operacionales, asistencia |
| **notifications** | Push, email, SMS |
| **sync** | Sincronización offline, cola de cambios |
| **reports** | Reportes, dashboards, exportaciones |
| **integrations** | Integraciones con sistemas externos |

---

## 4. Fases de Desarrollo

### Fase 0: Preparación y Setup (Semanas 1-2)

#### Objetivos
- Establecer entorno de desarrollo
- Configurar infraestructura base GCP
- Definir estándares de código según Indunnova

#### Entregables

| Tarea | Descripción |
|-------|-------------|
| Repositorio | Setup con estructura Django estándar |
| CI/CD Pipeline | GitHub Actions + Cloud Build |
| Infraestructura base | Terraform para GCP |
| Ambientes | Dev (local), Staging, Production |
| Pre-commit hooks | Ruff, mypy, djLint |
| Diseño UI/UX | Wireframes y mockups en Figma |

#### Estructura del Proyecto

```
sd-lms/
├── apps/
│   ├── accounts/               # Usuarios y autenticación
│   │   ├── models.py
│   │   ├── views.py
│   │   ├── api/
│   │   │   ├── views.py        # DRF views
│   │   │   └── ninja.py        # Django Ninja endpoints
│   │   ├── services.py         # Service Layer
│   │   ├── repositories.py     # Repository Pattern
│   │   └── tests/
│   │
│   ├── courses/                # Gestión de cursos
│   ├── assessments/            # Evaluaciones
│   ├── certifications/         # Certificados
│   ├── learning_paths/         # Rutas de aprendizaje
│   ├── lessons_learned/        # Lecciones aprendidas
│   ├── preop_talks/           # Charlas pre-operacionales
│   ├── reports/               # Reportes y analytics
│   ├── sync/                  # Sincronización offline
│   └── notifications/         # Notificaciones
│
├── config/
│   ├── settings/
│   │   ├── base.py
│   │   ├── local.py
│   │   ├── staging.py
│   │   ├── production.py
│   │   └── test.py
│   ├── urls.py
│   ├── celery.py
│   └── wsgi.py
│
├── templates/                  # Django templates + HTMX
│   ├── base.html
│   ├── components/            # Componentes reutilizables
│   └── partials/              # Fragmentos HTMX
│
├── static/
│   ├── css/
│   │   └── tailwind.css
│   ├── js/
│   │   ├── htmx.min.js
│   │   └── alpine.min.js
│   └── vendor/
│
├── mobile/                     # React Native App
│   ├── src/
│   ├── package.json
│   └── app.json
│
├── infrastructure/
│   ├── terraform/
│   └── docker/
│
├── docs/
│   ├── mkdocs.yml
│   └── docs/
│
├── requirements/
│   ├── base.txt
│   ├── local.txt
│   ├── production.txt
│   └── test.txt
│
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml             # Ruff config
├── .pre-commit-config.yaml
└── README.md
```

---

### Fase 1: Core Backend y Autenticación (Semanas 3-6)

#### Objetivos
- Implementar aplicaciones Django core
- Sistema de autenticación robusto con 2FA
- Gestión de usuarios y roles

#### Módulos a Desarrollar

##### 1.1 App de Autenticación (accounts)
```python
# Funcionalidades
- Login con email/password
- Autenticación de dos factores (django-otp)
- Gestión de sesiones (Redis)
- Refresh tokens (djangorestframework-simplejwt)
- Logout y revocación de tokens
- Recuperación de contraseña
- Protección fuerza bruta (django-axes)
```

##### 1.2 Gestión de Usuarios
```python
# Funcionalidades
- CRUD de usuarios
- Gestión de perfiles (Admin, Supervisor, Colaborador, Auditor, Instructor)
- Asignación de roles y permisos (django-guardian)
- Vinculación con contratos
- Importación masiva (CSV/Excel con pandas)
- Histórico de contratos
- Estados de usuario (activo, inactivo, suspendido)
```

##### 1.3 Modelo de Datos (Django Models)

```python
# apps/accounts/models.py

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Status(models.TextChoices):
        ACTIVE = "active", "Activo"
        INACTIVE = "inactive", "Inactivo"
        SUSPENDED = "suspended", "Suspendido"
        PROBATION = "probation", "Período de Prueba"

    document_type = models.CharField(max_length=10)  # CC, CE, etc.
    document_number = models.CharField(max_length=20, unique=True)
    phone = models.CharField(max_length=20, blank=True)
    job_position = models.CharField(max_length=100)
    work_front = models.CharField(max_length=100, blank=True)
    hire_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    class Meta:
        db_table = "users"


class Role(models.Model):
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    permissions = models.ManyToManyField("auth.Permission")
    users = models.ManyToManyField(User, related_name="custom_roles")

    class Meta:
        db_table = "roles"


class Contract(models.Model):
    code = models.CharField(max_length=50, unique=True)  # ej: "ISA 4620004459"
    name = models.CharField(max_length=200)
    client = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "contracts"


class UserContract(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="contracts")
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="users")
    assigned_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "user_contracts"
        unique_together = ["user", "contract"]
```

#### Entregables Fase 1
- [ ] App accounts con autenticación completa
- [ ] API REST (DRF) + API rápida (Django Ninja)
- [ ] Sistema de roles y permisos
- [ ] Importación masiva de usuarios
- [ ] Documentación API (drf-spectacular)
- [ ] Tests unitarios y de integración (cobertura >80%)
- [ ] Templates HTMX para admin de usuarios

---

### Fase 2: Gestión de Contenidos (LCMS) (Semanas 7-10)

#### Objetivos
- Sistema de gestión de cursos
- Soporte para múltiples formatos de contenido
- Versionamiento de contenidos

#### Módulos a Desarrollar

##### 2.1 App de Cursos (courses)
```python
# Funcionalidades
- CRUD de cursos
- Módulos y lecciones
- Soporte multimedia (video, PDF, audio, imágenes)
- Contenido SCORM (1.2 y 2004)
- Versionamiento de contenido
- Categorización (tema, riesgo, obligatoriedad)
- Estados (borrador, publicado, archivado)
```

##### 2.2 Procesamiento Multimedia (Celery Tasks)
```python
# Funcionalidades
- Upload de archivos (chunked para videos grandes)
- Procesamiento de video (FFmpeg, transcoding, compresión)
- Generación de thumbnails
- Cloud Storage + CDN integration
- Soporte offline (manifest de descarga)
- Biblioteca de recursos
```

##### 2.3 Modelo de Datos

```python
# apps/courses/models.py

from django.db import models
from django.contrib.postgres.fields import ArrayField


class Course(models.Model):
    class Type(models.TextChoices):
        MANDATORY = "mandatory", "Obligatorio"
        OPTIONAL = "optional", "Opcional"
        REFRESHER = "refresher", "Refuerzo"

    class Status(models.TextChoices):
        DRAFT = "draft", "Borrador"
        PUBLISHED = "published", "Publicado"
        ARCHIVED = "archived", "Archivado"

    class RiskLevel(models.TextChoices):
        LOW = "low", "Bajo"
        MEDIUM = "medium", "Medio"
        HIGH = "high", "Alto"
        CRITICAL = "critical", "Crítico"

    code = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField()
    duration = models.PositiveIntegerField(help_text="Duración en minutos")
    course_type = models.CharField(max_length=20, choices=Type.choices)
    risk_level = models.CharField(max_length=20, choices=RiskLevel.choices)
    thumbnail_url = models.URLField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    version = models.PositiveIntegerField(default=1)
    target_profiles = ArrayField(models.CharField(max_length=50), default=list)
    prerequisites = models.ManyToManyField("self", symmetrical=False, blank=True)
    created_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "courses"


class Module(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="modules")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField()

    class Meta:
        db_table = "modules"
        ordering = ["order"]


class Lesson(models.Model):
    class Type(models.TextChoices):
        VIDEO = "video", "Video"
        PDF = "pdf", "PDF"
        SCORM = "scorm", "SCORM"
        INTERACTIVE = "interactive", "Interactivo"
        QUIZ = "quiz", "Quiz"
        AUDIO = "audio", "Audio"

    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="lessons")
    title = models.CharField(max_length=200)
    lesson_type = models.CharField(max_length=20, choices=Type.choices)
    content_url = models.URLField()
    offline_url = models.URLField(blank=True, help_text="URL comprimida para offline")
    duration = models.PositiveIntegerField(help_text="Duración en minutos")
    order = models.PositiveIntegerField()
    is_offline_available = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict)

    class Meta:
        db_table = "lessons"
        ordering = ["order"]


class MediaAsset(models.Model):
    class Status(models.TextChoices):
        PROCESSING = "processing", "Procesando"
        READY = "ready", "Listo"
        ERROR = "error", "Error"

    filename = models.CharField(max_length=255)
    original_name = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=100)
    size = models.PositiveBigIntegerField()
    url = models.URLField()
    thumbnail_url = models.URLField(blank=True)
    offline_url = models.URLField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PROCESSING)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "media_assets"
```

#### Entregables Fase 2
- [ ] App courses completa
- [ ] Sistema de upload y procesamiento multimedia (Celery)
- [ ] Soporte SCORM básico
- [ ] Biblioteca de recursos
- [ ] Editor de cursos con HTMX
- [ ] Versionamiento de contenidos

---

### Fase 3: Rutas de Aprendizaje y Evaluaciones (Semanas 11-14)

#### Objetivos
- Sistema de rutas de aprendizaje con prerrequisitos
- Motor de evaluaciones completo
- Sistema de certificación

#### Apps a Desarrollar

##### 3.1 App learning_paths
```python
# Funcionalidades
- Definición de rutas por perfil ocupacional
- Prerrequisitos y secuenciación
- Fechas límite y vencimientos
- Asignación automática según perfil
- Bloqueo de avance sin completar prerrequisitos
- Notificaciones de cursos pendientes/vencidos
```

##### 3.2 App assessments
```python
# Funcionalidades
- Banco de preguntas por tema
- Tipos: múltiple, V/F, ordenamiento, asociación
- Aleatorización de preguntas
- Tiempo límite configurable
- Intentos máximos configurables
- Retroalimentación inmediata
- Evaluación de escenarios (simulaciones)
- Evaluación práctica (checklist con firma digital)
```

##### 3.3 App certifications
```python
# Funcionalidades
- Generación de certificados PDF (WeasyPrint)
- Código QR de verificación
- Firma digital del responsable
- Fechas de vencimiento
- Alertas de renovación (30 días antes)
- Verificación pública de certificados
- Pasaporte de competencias
```

#### Entregables Fase 3
- [ ] App learning_paths completa
- [ ] App assessments con motor de evaluaciones
- [ ] App certifications con generación PDF
- [ ] Verificación QR de certificados
- [ ] Alertas de vencimiento (Celery Beat)

---

### Fase 4: Aplicación Móvil - Core (Semanas 15-18)

#### Objetivos
- App móvil funcional Android/iOS
- Capacidad offline completa
- Sincronización robusta

#### Módulos a Desarrollar

##### 4.1 Core Mobile (React Native)
```typescript
// Funcionalidades
- Autenticación biométrica
- Dashboard personal
- Navegación de cursos
- Reproductor de contenido
- Realización de evaluaciones
- Visualización de certificados
```

##### 4.2 Sistema Offline
```typescript
// Funcionalidades
- Descarga selectiva de cursos
- Base de datos local (WatermelonDB)
- Cola de sincronización
- Resolución de conflictos
- Indicador de estado de sincronización
- Gestión de almacenamiento
- Compresión de contenido offline
```

##### 4.3 Arquitectura Offline

```
┌─────────────────────────────────────────────────────────────┐
│                      REACT NATIVE APP                        │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   UI Layer  │  │ State Mgmt  │  │  Offline Manager    │  │
│  │  (Screens)  │  │  (Zustand)  │  │                     │  │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
│         │                │                     │             │
│         └────────────────┼─────────────────────┘             │
│                          │                                   │
│  ┌───────────────────────▼───────────────────────────────┐  │
│  │                   Repository Layer                     │  │
│  │  ┌─────────────────┐     ┌─────────────────────────┐  │  │
│  │  │  Online Repo    │     │     Offline Repo        │  │  │
│  │  │   (API Client)  │     │   (WatermelonDB)        │  │  │
│  │  └────────┬────────┘     └───────────┬─────────────┘  │  │
│  │           │                          │                 │  │
│  │  ┌────────▼────────────────────────▼──────────────┐   │  │
│  │  │              Sync Engine                        │   │  │
│  │  │  - Conflict Resolution                          │   │  │
│  │  │  - Queue Management                             │   │  │
│  │  │  - Background Sync                              │   │  │
│  │  └─────────────────────────────────────────────────┘   │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │                 Local Storage                          │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  │  │
│  │  │ WatermelonDB │  │    MMKV      │  │ File System │  │  │
│  │  │  (SQL Data)  │  │  (Key-Value) │  │  (Media)    │  │  │
│  │  └──────────────┘  └──────────────┘  └─────────────┘  │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

#### Entregables Fase 4
- [ ] App móvil funcional (Android + iOS)
- [ ] Sistema de descarga offline
- [ ] Reproductor de video offline
- [ ] Evaluaciones offline
- [ ] Sincronización automática
- [ ] Push notifications (Firebase)

---

### Fase 5: Lecciones Aprendidas y Charlas Pre-Operacionales (Semanas 19-22)

#### Apps a Desarrollar

##### 5.1 App lessons_learned
```python
# Funcionalidades
- Creación de lecciones (plantilla estandarizada)
- Categorización (accidente, casi-accidente, buena práctica)
- Vinculación con cursos relacionados
- Generación automática de micro-learning
- Notificación a todo el personal
- Quiz de comprensión
- Histórico de visualizaciones
```

##### 5.2 App preop_talks
```python
# Funcionalidades
- Biblioteca de charlas de 5 minutos
- Selección según actividad del día
- Registro de asistencia (QR + geolocalización)
- Foto grupal opcional
- Pregunta "¿Qué puede salir mal hoy?"
- Mini-evaluación de 3 preguntas
- Recordatorio de SWA recientes
- Funcionamiento offline
```

#### Entregables Fase 5
- [ ] App lessons_learned completa
- [ ] Generador de micro-learning
- [ ] App preop_talks
- [ ] Registro de asistencia con QR
- [ ] Geolocalización de charlas
- [ ] Funcionamiento offline completo

---

### Fase 6: Reportes y Analytics (Semanas 23-26)

#### Objetivos
- Dashboards para todos los perfiles
- Reportes exportables
- Integración con operaciones

#### App reports

##### 6.1 Dashboards (HTMX + ECharts)
```python
# Dashboards
- Cumplimiento general del plan de formación
- Trabajadores con formación vencida
- Brechas de competencias por contrato
- Horas de formación ejecutadas vs planificadas
- Ranking de módulos con mayor reprobación
- Estado de formación por equipo
```

##### 6.2 Reportes Exportables
```python
# Reportes
- Matriz de competencias (Excel)
- Certificaciones vigentes/vencidas (PDF/Excel)
- Registro de charlas pre-operacionales
- Detalle de evaluaciones
- Informe para ARL
- Informe para auditorías SST
```

##### 6.3 Portal Auditor ISA
```python
# Funcionalidades (solo lectura)
- Dashboard de cumplimiento
- Evidencias de formación
- Histórico de formación por trabajador
- Exportación de reportes
- Verificación de certificados
```

#### Entregables Fase 6
- [ ] Dashboard administrativo
- [ ] Dashboard supervisores
- [ ] Portal auditor ISA
- [ ] Reportes exportables (PDF, Excel)
- [ ] API de integración con operaciones
- [ ] Alertas automáticas

---

### Fase 7: Gamificación y Notificaciones (Semanas 27-28)

#### Sistema de Gamificación
```python
# Elementos
- Puntos por completar cursos y evaluaciones
- Insignias (Experto en Altura, Héroe SWA, etc.)
- Rankings por cuadrilla e individual
- Progreso visual (barras, mapas)
- Reconocimientos especiales
```

#### Sistema de Notificaciones
```python
# Canales
- Push notifications (Firebase FCM)
- Email (SendGrid)
- SMS (Twilio) para urgentes

# Eventos
- Nuevo curso asignado
- Curso próximo a vencer
- Curso vencido
- Nueva lección aprendida
- Certificado emitido
- Evaluación reprobada
```

#### Entregables Fase 7
- [ ] Sistema de puntos e insignias
- [ ] Rankings y leaderboards
- [ ] Notificaciones push, email, SMS
- [ ] Panel de configuración de notificaciones

---

### Fase 8: Pruebas, Optimización y Despliegue (Semanas 29-32)

#### Testing (Alineado con Indunnova)
```python
# Stack de testing
- pytest-django (cobertura >80%)
- factory_boy + faker
- playwright (E2E web)
- Detox (E2E móvil)
- k6 (pruebas de carga)
- OWASP ZAP (seguridad)
```

#### Optimización
```python
# Mejoras de rendimiento
- django-cachalot (cache de QuerySets)
- Query optimization (select_related, prefetch_related)
- Redis caching
- WhiteNoise (archivos estáticos)
- Lazy loading de componentes
```

#### Despliegue
```python
# Producción
- Cloud Run deployment
- Cloud SQL configuración final
- Monitoreo con Sentry + Cloud Monitoring
- Runbooks operativos
- Capacitación a administradores
```

#### Entregables Fase 8
- [ ] Suite de tests completa (>80% cobertura)
- [ ] Documentación de usuario (MkDocs)
- [ ] Manual de administrador
- [ ] Runbooks operativos
- [ ] Sistema desplegado en producción
- [ ] Capacitación completada

---

## 5. Cronograma General

```
                            2026
        ENE     FEB     MAR     ABR     MAY     JUN     JUL     AGO
        ─────────────────────────────────────────────────────────────
Fase 0  ████                                                          Setup
Fase 1      ████████                                                  Auth & Users
Fase 2              ████████                                          LCMS
Fase 3                      ████████                                  Learning Paths
Fase 4                              ████████                          Mobile Core
Fase 5                                      ████████                  Lecciones
Fase 6                                              ████████          Reportes
Fase 7                                                      ████      Gamificación
Fase 8                                                          ████  Deploy

        S1-2    S3-6    S7-10   S11-14  S15-18  S19-22  S23-26  S27-32
```

---

## 6. Equipo Recomendado

### Equipo Core

| Rol | Cantidad | Responsabilidades |
|-----|----------|-------------------|
| **Tech Lead / Arquitecto** | 1 | Arquitectura Django, decisiones técnicas, code review |
| **Backend Developer Senior (Python/Django)** | 2 | APIs, servicios, Celery tasks |
| **Frontend Developer (Django + HTMX)** | 1 | Templates, HTMX, Alpine.js, Tailwind |
| **Mobile Developer Senior (React Native)** | 2 | App móvil, offline, sincronización |
| **DevOps Engineer** | 1 | GCP, Cloud Run, CI/CD, monitoreo |
| **QA Engineer** | 1 | pytest, playwright, automatización |
| **UX/UI Designer** | 1 | Diseño de interfaces, experiencia de usuario |

### Equipo Extendido

| Rol | Cantidad | Responsabilidades |
|-----|----------|-------------------|
| **Product Owner** | 1 (cliente) | Priorización, validación |
| **Scrum Master** | 1 | Facilitación, mejora continua |
| **Diseñador Instruccional** | 1 | Contenido educativo |

---

## 7. Riesgos y Mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| Complejidad del modo offline | Alta | Alto | PoC temprano en Fase 0, experto en sync |
| Conectividad en zonas remotas | Alta | Alto | Diseño offline-first, compresión agresiva |
| Adopción por usuarios operativos | Media | Alto | UX simple, capacitación, gamificación |
| Integración SCORM | Media | Medio | Usar librería probada |
| Escalabilidad | Baja | Alto | Cloud Run auto-scaling, CQRS para reportes |
| Cumplimiento normativo | Baja | Alto | Revisión legal temprana, cifrado |

---

## 8. Métricas de Éxito Técnico

| Métrica | Target |
|---------|--------|
| Tiempo de carga inicial (web) | < 3s |
| Tiempo de carga inicial (móvil) | < 2s |
| Uptime | 99.5% |
| Sincronización offline | < 30s para 1 día de trabajo |
| Cobertura de tests | > 80% |
| Tamaño de APK | < 50MB |
| Memoria máxima (móvil) | < 200MB |
| Latencia API P95 | < 200ms |

---

## 9. Próximos Pasos Inmediatos

1. **Validar este plan** con stakeholders de S.D. S.A.S.
2. **Definir MVP** - Priorizar funcionalidades para primera release
3. **Configurar repositorio** y ambiente de desarrollo
4. **Setup pre-commit hooks** (Ruff, mypy, djLint)
5. **Iniciar diseño UX/UI** de las pantallas principales
6. **Comenzar Fase 0** - Setup de infraestructura GCP base

---

## 10. Documentos Relacionados

| Documento | Descripción |
|-----------|-------------|
| [Arquitectura GCP](./ARQUITECTURA_INFRAESTRUCTURA_GCP.md) | Propuesta de infraestructura Google Cloud |
| [Alineación Indunnova](./ALINEACION_ESTANDAR_INDUNNOVA.md) | Comparativa con estándar Indunnova v2.0 |
| [Especificación Funcional](../ESPECIFICACION_FUNCIONAL.md) | Requisitos detallados del sistema |

---

*Documento generado como parte del plan de desarrollo del Sistema LMS para S.D. S.A.S., alineado con el Estándar de Infraestructura Tecnológica de Indunnova SAS v2.0*
