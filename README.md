# Sistema LMS - S.D. S.A.S.

## Sistema de Gestión de Capacitaciones y Plan de Formación

Sistema integral de gestión del aprendizaje (LMS) diseñado para garantizar que el personal de S.D. S.A.S. que opera en líneas de transmisión eléctrica cuente con las competencias necesarias para ejecutar trabajos de alto riesgo de manera segura.

**Alineado con:** Estándar de Infraestructura Tecnológica Indunnova SAS v2.0

---

## Documentación

| Documento | Descripción |
|-----------|-------------|
| [Plan de Desarrollo](./docs/PLAN_DE_DESARROLLO.md) | Fases, cronograma, stack tecnológico y equipo |
| [Arquitectura GCP](./docs/ARQUITECTURA_INFRAESTRUCTURA_GCP.md) | Propuesta de infraestructura Google Cloud |
| [Alineación Indunnova](./docs/ALINEACION_ESTANDAR_INDUNNOVA.md) | Comparativa con estándar Indunnova v2.0 |

---

## Características Principales

- **Gestión de Usuarios**: Perfiles diferenciados (Admin, Supervisor, Colaborador, Auditor, Instructor)
- **LCMS**: Sistema de gestión de contenidos educativos con soporte multimedia
- **Rutas de Aprendizaje**: Secuenciación de cursos con prerrequisitos
- **Evaluaciones**: Teóricas, prácticas y de escenarios
- **Certificaciones**: Generación automática con QR de verificación
- **Lecciones Aprendidas**: Repositorio con generación de micro-learning
- **Charlas Pre-Operacionales**: Registro digital con geolocalización
- **Modo Offline**: Funcionamiento completo sin conectividad
- **Reportes y Analytics**: Dashboards para todos los perfiles

---

## Stack Tecnológico (Alineado con Indunnova v2.0)

### Backend
- **Framework**: Python 3.12 + Django 5.1 LTS
- **APIs**: Django REST Framework 3.15+ + Django Ninja
- **Base de Datos**: PostgreSQL 16
- **Caché**: Redis 7.x
- **Tareas Async**: Celery + Redis

### Frontend Web
- **Interactividad**: HTMX 2.x + Alpine.js 3.x
- **Estilos**: Tailwind CSS 3.x + daisyUI
- **Gráficos**: Apache ECharts + AG Grid

### Frontend Móvil
- **Framework**: React Native + Expo
- **Offline**: WatermelonDB + MMKV

### Infraestructura (GCP)
- **Cloud**: Google Cloud Platform (southamerica-east1)
- **Compute**: Cloud Run (serverless)
- **Database**: Cloud SQL PostgreSQL 16
- **Cache**: Memorystore Redis
- **Storage**: Cloud Storage + Cloud CDN
- **CI/CD**: GitHub Actions + Cloud Build
- **IaC**: Terraform

---

## Estructura del Proyecto

```
sd-lms/
├── apps/
│   ├── accounts/            # Usuarios y autenticación
│   ├── courses/             # Gestión de cursos
│   ├── assessments/         # Evaluaciones
│   ├── certifications/      # Certificados
│   ├── learning_paths/      # Rutas de aprendizaje
│   ├── lessons_learned/     # Lecciones aprendidas
│   ├── preop_talks/         # Charlas pre-operacionales
│   ├── reports/             # Reportes y analytics
│   ├── sync/                # Sincronización offline
│   └── notifications/       # Notificaciones
├── config/
│   ├── settings/            # Configuraciones Django
│   ├── urls.py
│   └── celery.py
├── templates/               # Django templates + HTMX
├── static/                  # CSS, JS, assets
├── mobile/                  # React Native app
├── infrastructure/
│   ├── terraform/           # IaC
│   └── docker/              # Dockerfiles
├── docs/                    # Documentación
└── requirements/            # Dependencies
```

---

## Requisitos del Sistema

### Desarrollo
- Python 3.12+
- Node.js 20+ (para móvil)
- Docker Desktop
- Google Cloud CLI

### Producción
- GCP Project con billing habilitado
- Dominio configurado en Cloud DNS
- Certificados SSL (gestionados por GCP)

---

## Inicio Rápido

```bash
# Clonar repositorio
git clone <repository-url>
cd sd-lms

# Crear entorno virtual Python
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Instalar dependencias
pip install -r requirements/local.txt

# Configurar variables de entorno
cp .env.example .env

# Iniciar servicios con Docker
docker-compose up -d db redis

# Ejecutar migraciones
python manage.py migrate

# Crear superusuario
python manage.py createsuperuser

# Iniciar servidor de desarrollo
python manage.py runserver
```

---

## Testing

```bash
# Ejecutar tests
pytest

# Con cobertura
pytest --cov=apps --cov-report=html

# Linting
ruff check .
ruff format .

# Type checking
mypy apps/
```

---

## Licencia

Propiedad de S.D. S.A.S. - Todos los derechos reservados.

---

*Proyecto desarrollado para garantizar la seguridad y competencia del personal en trabajos de alto riesgo en líneas de transmisión eléctrica.*
# Test
