# Alineación con Estándar Indunnova SAS v2.0

## Sistema LMS S.D. S.A.S.

**Fecha:** Enero 2026
**Estándar de Referencia:** Indunnova SAS v2.0 (Diciembre 2025)

---

## 1. Resumen Ejecutivo

Este documento detalla cómo el Sistema LMS de S.D. S.A.S. se alinea con el Estándar de Infraestructura Tecnológica de Indunnova SAS v2.0, identificando componentes alineados, adaptaciones necesarias y justificaciones para cualquier desviación.

### 1.1 Nivel de Alineación General

| Categoría | Alineación | Observación |
|-----------|------------|-------------|
| **Backend** | 95% | Totalmente alineado con Django/Python |
| **Frontend Web** | 100% | HTMX + Alpine.js + Tailwind |
| **Frontend Móvil** | N/A* | React Native (no especificado en estándar) |
| **DevOps** | 90% | GCP en lugar de DigitalOcean |
| **Testing** | 100% | pytest + Ruff + mypy |
| **Seguridad** | 100% | Todas las librerías recomendadas |

*El estándar Indunnova no especifica stack móvil. React Native se selecciona por requerimientos de offline.

---

## 2. Backend - Alineación Detallada

### 2.1 Framework y Lenguaje

| Componente | Estándar Indunnova | SD LMS | Estado | Notas |
|------------|-------------------|--------|--------|-------|
| Python | 3.12.x / 3.13.x | 3.12.x | ✅ | Mejoras de rendimiento 10-15% |
| Django | 5.1.x LTS | 5.1.x LTS | ✅ | Soporte async nativo mejorado |
| PostgreSQL | 16.x / 17.x | 16.x | ✅ | Cloud SQL managed |

### 2.2 APIs y Servicios

| Tecnología | Estándar | SD LMS | Estado | Uso en LMS |
|------------|----------|--------|--------|------------|
| Django REST Framework | 3.15+ | 3.15+ | ✅ | APIs REST principales |
| Django Ninja | Nuevo | Implementado | ✅ | APIs de alto rendimiento (sync service) |
| GraphQL (Strawberry) | Nuevo | Fase 2 | ⏳ | Para dashboards complejos |
| OpenAPI/Swagger | Sí | drf-spectacular | ✅ | Documentación automática |

### 2.3 Arquitectura y Patrones

```
┌─────────────────────────────────────────────────────────────┐
│              ARQUITECTURA SD LMS (Alineada)                  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│  │  Cloud   │───▶│  Django  │───▶│Cloud SQL │              │
│  │   LB     │    │ Cloud Run│    │PostgreSQL│              │
│  │          │    │          │    │    16    │              │
│  └──────────┘    └────┬─────┘    └──────────┘              │
│                       │                                      │
│       ┌───────────────┼───────────────┐                     │
│       ▼               ▼               ▼                     │
│  ┌─────────┐    ┌──────────┐    ┌──────────┐              │
│  │Memorystore    │  Cloud   │    │  Cloud   │              │
│  │  Redis  │    │  Tasks   │    │ Storage  │              │
│  │ (Cache) │    │ (Celery) │    │ (Files)  │              │
│  └─────────┘    └──────────┘    └──────────┘              │
│                                                              │
│  Equivalencia con Estándar:                                  │
│  ├─ NGINX → Cloud Load Balancer                             │
│  ├─ Redis → Memorystore Redis                               │
│  ├─ Celery Workers → Cloud Run Jobs                         │
│  └─ MinIO/S3 → Cloud Storage                                │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

| Patrón | Estándar | SD LMS | Implementación |
|--------|----------|--------|----------------|
| Repository Pattern | ✅ | ✅ | `apps/*/repositories.py` |
| Service Layer | ✅ | ✅ | `apps/*/services.py` |
| CQRS simplificado | ✅ | ✅ | Read replicas para reportes |
| Event-Driven | ✅ | ✅ | Celery + Django signals |
| Clean Architecture | ✅ | ✅ | Separación clara de capas |

### 2.4 Caché y Rendimiento

| Componente | Estándar | SD LMS | Estado |
|------------|----------|--------|--------|
| Redis 7.x | ✅ | Memorystore 7.x | ✅ |
| django-cachalot | ✅ | ✅ | Invalidación automática |
| WhiteNoise | ✅ | ✅ | Archivos estáticos |
| Connection Pooling | pgBouncer | Cloud SQL Proxy | ✅ Equivalente |

### 2.5 Tareas Asíncronas

```python
# Configuración Celery - Alineada con Estándar
# config/celery.py

CELERY_CONFIG = {
    "broker_url": env("REDIS_URL"),
    "result_backend": "django-db",
    "beat_scheduler": "django_celery_beat.schedulers:DatabaseScheduler",
    "task_queues": {
        "high_priority": {"exchange": "high"},  # Notificaciones urgentes
        "default": {"exchange": "default"},  # Tareas normales
        "reports": {"exchange": "reports"},  # Reportes pesados
        "media": {"exchange": "media"},  # Procesamiento multimedia
        "sync": {"exchange": "sync"},  # Sincronización offline
    },
    "task_routes": {
        "apps.notifications.*": {"queue": "high_priority"},
        "apps.reports.*": {"queue": "reports"},
        "apps.media.*": {"queue": "media"},
        "apps.sync.*": {"queue": "sync"},
    },
}
```

### 2.6 Seguridad Backend

| Librería | Estándar | SD LMS | Propósito |
|----------|----------|--------|-----------|
| django-axes | ✅ | ✅ | Protección fuerza bruta |
| django-csp | ✅ | ✅ | Content Security Policy |
| django-cors-headers | ✅ | ✅ | CORS configurado |
| django-otp | ✅ | ✅ | Autenticación 2FA |
| mozilla-django-oidc | Opcional | Firebase Auth | SSO alternativo |
| python-decouple | ✅ | ✅ | Variables de entorno |
| Secrets Manager | AWS/Vault | GCP Secret Manager | ✅ Equivalente |

---

## 3. Frontend - Alineación Detallada

### 3.1 Enfoque Híbrido Moderno

| Tecnología | Estándar | SD LMS Web | SD LMS Móvil | Justificación |
|------------|----------|------------|--------------|---------------|
| HTMX 2.x | ✅ | ✅ | N/A | Interactividad sin JS complejo |
| Alpine.js 3.x | ✅ | ✅ | N/A | Reactividad ligera (15KB) |
| Tailwind CSS 3.x | ✅ | ✅ | N/A | Utility-first |
| Hyperscript | ✅ | ✅ | N/A | Scripting declarativo |
| React Native | N/A | N/A | ✅ | Requerimiento offline |

### 3.2 Stack CSS

```
┌────────────────────────────────────────┐
│  Tailwind CSS 3.x (Opción A)           │
│  + daisyUI (componentes prediseñados)  │  ✅ Implementado
│  + @tailwindcss/forms                  │
│  + @tailwindcss/typography             │
└────────────────────────────────────────┘
```

### 3.3 JavaScript Moderno

| Componente | Estándar | SD LMS | Estado |
|------------|----------|--------|--------|
| ES6+ Modules | ✅ | ✅ | Código modular |
| Fetch API + async/await | ✅ | ✅ | Nativo, más limpio |
| Alpine.js | ✅ | ✅ | Reactivo, declarativo |
| Vite | ✅ | ✅ | Build rápido, HMR |

### 3.4 Visualización de Datos

| Librería | Estándar | SD LMS | Uso |
|----------|----------|--------|-----|
| Apache ECharts | ✅ | ✅ | Dashboards complejos |
| Chart.js 4.x | ✅ | ✅ | Gráficos simples |
| D3.js | ✅ | Opcional | Visualizaciones custom |
| Plotly.js | ✅ | Opcional | Gráficos científicos |
| AG Grid Community | ✅ | ✅ | Tablas avanzadas |

### 3.5 Componentes UI

```
┌─────────────────────────────────────────────────────────┐
│               COMPONENTES FRONTEND SD LMS                │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  Formularios:          │  Tablas:                       │
│  ├─ django-crispy ✅   │  ├─ AG Grid ✅                 │
│  ├─ django-widget-     │  ├─ Exportación Excel/PDF ✅   │
│  │   tweaks ✅         │  └─ Paginación server-side ✅  │
│  └─ Tom Select ✅      │                                │
│     (selects avanzados)│  Feedback:                     │
│                        │  ├─ SweetAlert2 ✅             │
│  Uploads:              │  ├─ Toastify ✅                │
│  ├─ FilePond ✅        │  └─ Loading skeletons ✅       │
│  └─ Drag & Drop ✅     │                                │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## 4. DevOps e Infraestructura - Alineación

### 4.1 Contenedorización

| Aspecto | Estándar | SD LMS | Notas |
|---------|----------|--------|-------|
| Docker | ✅ | ✅ | Dockerfile multi-stage |
| docker-compose (dev) | ✅ | ✅ | Desarrollo local |
| PostgreSQL 16-alpine | ✅ | Cloud SQL | Managed service |
| Redis 7-alpine | ✅ | Memorystore | Managed service |
| Celery workers | ✅ | Cloud Run Jobs | Serverless |

```yaml
# docker-compose.yml (Desarrollo Local - Alineado)
services:
  web:
    build:
      context: .
      dockerfile: docker/Dockerfile
    ports:
      - "8000:8000"
    env_file: .env
    volumes:
      - .:/app
    depends_on:
      - db
      - redis

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: sdlms
      POSTGRES_USER: sdlms
      POSTGRES_PASSWORD: sdlms
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  celery:
    build:
      context: .
      dockerfile: docker/Dockerfile
    command: celery -A config worker -l INFO
    env_file: .env
    depends_on:
      - db
      - redis

  celery-beat:
    build:
      context: .
      dockerfile: docker/Dockerfile
    command: celery -A config beat -l INFO
    env_file: .env
    depends_on:
      - db
      - redis

volumes:
  postgres_data:
```

### 4.2 CI/CD Pipeline

```
┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
│  Test   │───▶│  Build  │───▶│ Deploy  │───▶│ Monitor │
│         │    │         │    │         │    │         │
│• pytest │    │• Docker │    │• Staging│    │• Sentry │  ✅ Alineado
│• ruff   │    │• Push   │    │• Prod   │    │• Logs   │
│• mypy   │    │Registry │    │         │    │         │
└─────────┘    └─────────┘    └─────────┘    └─────────┘

Estándar: GitHub Actions / GitLab CI
SD LMS:   GitHub Actions + Cloud Build  ✅
```

### 4.3 Monitoreo y Observabilidad

| Herramienta | Estándar | SD LMS | Estado |
|-------------|----------|--------|--------|
| Sentry | ✅ | ✅ | Error tracking + performance |
| Prometheus + Grafana | ✅ | Cloud Monitoring | ✅ Equivalente |
| Loki | ✅ | Cloud Logging | ✅ Equivalente |
| Uptime Kuma | ✅ | Cloud Monitoring Uptime | ✅ Equivalente |
| django-silk | ✅ | ✅ | Profiling en desarrollo |

### 4.4 Infraestructura Cloud

| Opción | Estándar | SD LMS | Justificación |
|--------|----------|--------|---------------|
| DigitalOcean/Railway | Recomendado | No | Mayor escala requerida |
| AWS/GCP Enterprise | Alternativa | **GCP** | ✅ Seleccionado por costos LATAM |

**Justificación de GCP sobre DigitalOcean:**
1. Requerimiento de 200-1000 usuarios concurrentes
2. Procesamiento de video pesado
3. Alta disponibilidad (99.5% SLA)
4. Sincronización offline robusta
5. Mejor pricing en región LATAM

---

## 5. Testing y Calidad de Código

### 5.1 Stack de Testing

```ini
# pytest.ini - Alineado con Estándar
[pytest]
DJANGO_SETTINGS_MODULE = config.settings.test
addopts = --cov=apps --cov-report=html --cov-fail-under=80
python_files = test_*.py
python_classes = Test*
python_functions = test_*
```

| Herramienta | Estándar | SD LMS | Propósito |
|-------------|----------|--------|-----------|
| pytest-django | ✅ | ✅ | Testing framework |
| factory_boy | ✅ | ✅ | Factories para fixtures |
| faker | ✅ | ✅ | Datos de prueba |
| pytest-cov | ✅ | ✅ | Cobertura (>80%) |
| playwright | ✅ | ✅ | E2E testing web |
| hypothesis | ✅ | ✅ | Property-based testing |

### 5.2 Calidad de Código

```yaml
# .pre-commit-config.yaml - Alineado con Estándar
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.9
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.8.0
    hooks:
      - id: mypy
        additional_dependencies:
          - django-stubs
          - djangorestframework-stubs

  - repo: https://github.com/Riverside-Healthcare/djLint
    rev: v1.34.1
    hooks:
      - id: djlint-django
```

| Herramienta | Estándar | SD LMS | Propósito |
|-------------|----------|--------|-----------|
| Ruff | ✅ | ✅ | Linter + formatter ultrarrápido |
| mypy | ✅ | ✅ | Type checking estático |
| pre-commit | ✅ | ✅ | Hooks de Git |
| djLint | ✅ | ✅ | Linting de templates Django |
| SonarQube | ✅ | Opcional | Análisis de seguridad |

---

## 6. Documentación

| Herramienta | Estándar | SD LMS | Propósito |
|-------------|----------|--------|-----------|
| MkDocs + Material | ✅ | ✅ | Documentación técnica |
| drf-spectacular | ✅ | ✅ | Documentación OpenAPI |
| Mermaid.js | ✅ | ✅ | Diagramas en markdown |
| ADR | ✅ | ✅ | Registro de decisiones |

---

## 7. Integraciones y APIs Externas

### 7.1 Servicios

| Servicio | Estándar | SD LMS | Uso |
|----------|----------|--------|-----|
| SendGrid / Amazon SES | ✅ | SendGrid | Emails transaccionales |
| Twilio | ✅ | Twilio | SMS y notificaciones |
| Stripe | Si aplica | N/A | No requerido |
| AWS S3 / MinIO | ✅ | Cloud Storage | Almacenamiento |
| OpenAI / Claude API | ✅ | Fase futura | IA para automatización |

### 7.2 Integraciones Adicionales (Específicas LMS)

| Integración | Propósito | Prioridad |
|-------------|-----------|-----------|
| SCORM Cloud | Contenido SCORM | Alta |
| Firebase FCM | Push notifications móvil | Alta |
| ISA Intercolombia API | Reportes al cliente | Media |
| Sistema de Nómina | Sync de usuarios | Baja |

---

## 8. Estructura del Proyecto

### 8.1 Estructura Django Alineada

```
sd-lms/
├── apps/
│   ├── accounts/               # Usuarios y autenticación
│   │   ├── models.py
│   │   ├── views.py
│   │   ├── serializers.py
│   │   ├── services.py         # ✅ Service Layer
│   │   ├── repositories.py     # ✅ Repository Pattern
│   │   └── tests/
│   │
│   ├── courses/                # Gestión de cursos
│   │   ├── models.py
│   │   ├── views.py
│   │   ├── api/
│   │   │   ├── views.py        # DRF views
│   │   │   └── ninja.py        # ✅ Django Ninja endpoints
│   │   ├── services.py
│   │   └── tests/
│   │
│   ├── assessments/            # Evaluaciones
│   ├── certifications/         # Certificados
│   ├── learning_paths/         # Rutas de aprendizaje
│   ├── lessons_learned/        # Lecciones aprendidas
│   ├── preop_talks/           # Charlas pre-operacionales
│   ├── reports/               # Reportes y analytics
│   ├── sync/                  # Sincronización offline
│   └── notifications/         # Sistema de notificaciones
│
├── config/
│   ├── settings/
│   │   ├── base.py
│   │   ├── local.py
│   │   ├── staging.py
│   │   ├── production.py
│   │   └── test.py
│   ├── urls.py
│   ├── celery.py              # ✅ Celery config
│   └── wsgi.py
│
├── templates/                  # ✅ Django templates + HTMX
│   ├── base.html
│   ├── components/            # ✅ Componentes reutilizables
│   └── partials/              # ✅ Fragmentos HTMX
│
├── static/
│   ├── css/
│   │   └── tailwind.css       # ✅ Tailwind
│   ├── js/
│   │   ├── htmx.min.js        # ✅ HTMX
│   │   └── alpine.min.js      # ✅ Alpine.js
│   └── vendor/
│
├── mobile/                     # React Native App
│   ├── src/
│   ├── package.json
│   └── app.json
│
├── infrastructure/
│   ├── terraform/
│   ├── kubernetes/
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
├── pyproject.toml             # ✅ Ruff config
├── .pre-commit-config.yaml    # ✅ Pre-commit hooks
└── README.md
```

---

## 9. Desviaciones y Justificaciones

### 9.1 Aplicación Móvil (React Native)

**Desviación:** El estándar Indunnova no especifica stack móvil. SD LMS utiliza React Native.

**Justificación:**
1. **Modo Offline Crítico:** El personal opera en zonas remotas sin conectividad
2. **Sincronización Compleja:** Requiere WatermelonDB para sync bidireccional
3. **Acceso a Hardware:** Cámara, GPS, firma digital, QR scanning
4. **Performance Nativa:** Reproducción de video offline, almacenamiento local

**Alternativas Consideradas:**
- PWA: Limitaciones de storage offline y background sync
- Ionic/Capacitor: Menor performance para video
- Flutter: Menor ecosistema para sincronización offline

### 9.2 GCP vs DigitalOcean

**Desviación:** Estándar recomienda DigitalOcean/Railway. SD LMS usa GCP.

**Justificación:**
| Factor | DigitalOcean | GCP | Decisión |
|--------|--------------|-----|----------|
| Usuarios concurrentes | 200 max | 1000+ | GCP |
| Video processing | Limitado | Cloud Run Jobs | GCP |
| Alta disponibilidad | Manual | Automática | GCP |
| Región LATAM | NYC/SF | São Paulo | GCP |
| Costo 200 usuarios | ~$300/mes | ~$800/mes | Aceptable |

### 9.3 GraphQL (Fase Posterior)

**Desviación:** Strawberry GraphQL se implementará en fase posterior.

**Justificación:**
- Fase 1-4: REST APIs son suficientes
- Fase 5+: Dashboards complejos se beneficiarán de GraphQL
- Mantiene complejidad inicial baja

---

## 10. Roadmap de Alineación

### Fase 1 (Meses 1-4): Core Alineado
- [x] Django 5.1 + Python 3.12
- [x] DRF 3.15 + Django Ninja
- [x] HTMX + Alpine.js + Tailwind
- [x] pytest + Ruff + mypy
- [x] Seguridad completa

### Fase 2 (Meses 5-6): Mejoras
- [ ] GraphQL (Strawberry) para dashboards
- [ ] SonarQube integration
- [ ] Performance tuning

### Fase 3 (Meses 7+): Optimización
- [ ] IA/ML integrations (Claude API)
- [ ] Analytics avanzados (BigQuery)
- [ ] Automatizaciones adicionales

---

## 11. Checklist de Cumplimiento

### Backend ✅
- [x] Python 3.12+
- [x] Django 5.1 LTS
- [x] PostgreSQL 16
- [x] Django REST Framework 3.15+
- [x] Django Ninja
- [x] Celery + Redis
- [x] Repository Pattern
- [x] Service Layer
- [x] CQRS (read replicas)
- [x] django-axes
- [x] django-csp
- [x] django-cors-headers
- [x] django-otp (2FA)
- [x] python-decouple

### Frontend ✅
- [x] HTMX 2.x
- [x] Alpine.js 3.x
- [x] Tailwind CSS 3.x
- [x] daisyUI
- [x] ES6+ Modules
- [x] Vite
- [x] Apache ECharts
- [x] AG Grid

### DevOps ✅
- [x] Docker
- [x] CI/CD Pipeline
- [x] Sentry
- [x] Cloud Monitoring (equiv. Prometheus)
- [x] Cloud Logging (equiv. Loki)
- [x] django-silk (desarrollo)

### Testing ✅
- [x] pytest-django
- [x] factory_boy
- [x] faker
- [x] pytest-cov (>80%)
- [x] playwright
- [x] Ruff
- [x] mypy
- [x] pre-commit
- [x] djLint

### Documentación ✅
- [x] MkDocs + Material
- [x] drf-spectacular
- [x] Mermaid.js
- [x] ADR

---

*Este documento certifica la alineación del Sistema LMS S.D. S.A.S. con el Estándar de Infraestructura Tecnológica de Indunnova SAS v2.0*
