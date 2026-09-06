# Arquitectura de Infraestructura - Sistema LMS S.D. S.A.S.

## Propuesta de Infraestructura Google Cloud Platform

**Versión:** 2.0
**Fecha:** Enero 2026
**Región Principal:** southamerica-east1 (São Paulo, Brasil)
**Alineación:** Estándar Indunnova SAS v2.0

---

## 1. Resumen de Infraestructura

### 1.1 Visión General

La infraestructura propuesta está diseñada sobre Google Cloud Platform, alineada con el estándar de Indunnova SAS, optimizada para una aplicación LMS crítica con soporte offline.

| Requisito | Especificación |
|-----------|----------------|
| **Disponibilidad** | 99.5% uptime (SLA GCP) |
| **Usuarios Concurrentes** | 200 inicial, escalable a 1,000 |
| **Almacenamiento** | 500GB inicial para multimedia |
| **Región** | LATAM (cumplimiento de datos Colombia) |
| **RTO** | < 4 horas |
| **RPO** | < 1 hora |

### 1.2 ¿Por qué Google Cloud?

| Factor | Justificación |
|--------|---------------|
| **Proximidad** | Región São Paulo con baja latencia a Colombia (~30-50ms) |
| **Cloud Run** | Serverless containers ideal para Django, sin gestión de infra |
| **Cloud SQL** | PostgreSQL gestionado con alta disponibilidad |
| **Precios Competitivos** | Descuentos por uso sostenido automáticos |
| **BigQuery** | Analytics de bajo costo para reportes complejos |
| **Firebase** | Excelente para push notifications y features móviles |

---

## 2. Stack Tecnológico Alineado con Indunnova

### 2.1 Comparativa de Stack

| Componente | Estándar Indunnova | Adaptación LMS S.D. |
|------------|-------------------|---------------------|
| **Backend** | Python 3.12+ / Django 5.1 LTS | Python 3.12 / Django 5.1 LTS |
| **Base de Datos** | PostgreSQL 16+ | Cloud SQL PostgreSQL 16 |
| **Caché** | Redis 7.x | Memorystore for Redis 7.x |
| **API** | Django REST Framework + Django Ninja | DRF 3.15 + Django Ninja |
| **Tareas Async** | Celery + Redis | Cloud Tasks + Celery |
| **Frontend Web** | HTMX + Alpine.js + Tailwind | HTMX + Alpine.js + Tailwind |
| **Frontend Móvil** | No especificado | React Native (requerido offline) |
| **Archivos** | MinIO / S3 | Cloud Storage |
| **CI/CD** | GitHub Actions | Cloud Build + GitHub Actions |

---

## 3. Diagrama de Arquitectura GCP

```
                                    ┌──────────────────────────────────────────┐
                                    │              INTERNET                     │
                                    └─────────────────────┬────────────────────┘
                                                          │
                                    ┌─────────────────────▼────────────────────┐
                                    │           Cloud DNS                       │
                                    │      (DNS + Health Checks)                │
                                    └─────────────────────┬────────────────────┘
                                                          │
                     ┌────────────────────────────────────┼────────────────────────────────────┐
                     │                                    │                                    │
          ┌──────────▼──────────┐            ┌───────────▼───────────┐           ┌────────────▼────────────┐
          │      Cloud CDN      │            │      Cloud CDN        │           │    Cloud Load Balancer  │
          │   (Static Assets)   │            │   (Media Delivery)    │           │      (HTTPS L7)         │
          └──────────┬──────────┘            └───────────┬───────────┘           └────────────┬────────────┘
                     │                                   │                                    │
          ┌──────────▼──────────┐            ┌───────────▼───────────┐                       │
          │   Cloud Storage     │            │    Cloud Storage      │                       │
          │  (Static Bucket)    │            │   (Media Bucket)      │                       │
          └─────────────────────┘            └───────────────────────┘                       │
                                                                                             │
                                    ┌────────────────────────────────────────────────────────┤
                                    │                                                        │
                                    │              Cloud Armor (WAF)                        │
                                    │                                                        │
                                    └────────────────────────────────────────────────────────┤
                                                                                             │
┌────────────────────────────────────────────────────────────────────────────────────────────┼─────────────────┐
│                                           VPC Network                                      │                 │
│                                                                                            │                 │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────┼───────────────┐ │
│  │                              Serverless VPC Access Connector                            │               │ │
│  └─────────────────────────────────────────────────────────────────────────────────────────┼───────────────┘ │
│                                                                                            │                 │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────┼───────────────┐ │
│  │                                      Cloud Run Services                                 │               │ │
│  │                                                                                         │               │ │
│  │  ┌─────────────────────────────────────────────────────────────────────────────────────▼─────────────┐ │ │
│  │  │                                                                                                    │ │ │
│  │  │  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐              │ │ │
│  │  │  │  Django Web App  │ │  Django API      │ │  Django Admin    │ │  Celery Workers  │              │ │ │
│  │  │  │  (Cloud Run)     │ │  (Cloud Run)     │ │  (Cloud Run)     │ │  (Cloud Run Jobs)│              │ │ │
│  │  │  │                  │ │                  │ │                  │ │                  │              │ │ │
│  │  │  │  - HTMX/Alpine   │ │  - DRF + Ninja   │ │  - Django Admin  │ │  - Background    │              │ │ │
│  │  │  │  - Tailwind CSS  │ │  - GraphQL       │ │  - Flower        │ │  - Reports       │              │ │ │
│  │  │  │  - WhiteNoise    │ │  - OpenAPI       │ │                  │ │  - Notifications │              │ │ │
│  │  │  └──────────────────┘ └──────────────────┘ └──────────────────┘ └──────────────────┘              │ │ │
│  │  │                                                                                                    │ │ │
│  │  │  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐                                   │ │ │
│  │  │  │  Media Processor │ │  PDF Generator   │ │  Sync Service    │                                   │ │ │
│  │  │  │  (Cloud Run Jobs)│ │  (Cloud Run Jobs)│ │  (Cloud Run)     │                                   │ │ │
│  │  │  │                  │ │                  │ │                  │                                   │ │ │
│  │  │  │  - FFmpeg        │ │  - WeasyPrint    │ │  - Offline Sync  │                                   │ │ │
│  │  │  │  - Video Trans.  │ │  - Certificates  │ │  - Conflict Res. │                                   │ │ │
│  │  │  └──────────────────┘ └──────────────────┘ └──────────────────┘                                   │ │ │
│  │  │                                                                                                    │ │ │
│  │  └────────────────────────────────────────────────────────────────────────────────────────────────────┘ │ │
│  │                                                                                                          │ │
│  └──────────────────────────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                                               │
│  ┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │                                        Managed Services                                                │  │
│  │                                                                                                        │  │
│  │  ┌─────────────────────────┐    ┌─────────────────────────┐    ┌─────────────────────────┐            │  │
│  │  │    Cloud SQL            │    │   Memorystore Redis     │    │    Cloud Tasks          │            │  │
│  │  │    PostgreSQL 16        │    │      (7.x)               │    │    (Task Queue)         │            │  │
│  │  │                         │    │                          │    │                         │            │  │
│  │  │  - High Availability    │    │  - Cache                 │    │  - Celery Broker Alt.   │            │  │
│  │  │  - Auto backups         │    │  - Sessions              │    │  - Scheduled Tasks      │            │  │
│  │  │  - 100GB SSD            │    │  - Celery Broker         │    │                         │            │  │
│  │  └─────────────────────────┘    └─────────────────────────┘    └─────────────────────────┘            │  │
│  │                                                                                                        │  │
│  │  ┌─────────────────────────┐    ┌─────────────────────────┐    ┌─────────────────────────┐            │  │
│  │  │    Secret Manager       │    │    Cloud Logging        │    │    Cloud Monitoring     │            │  │
│  │  │                         │    │    + Error Reporting    │    │    + Alerting           │            │  │
│  │  └─────────────────────────┘    └─────────────────────────┘    └─────────────────────────┘            │  │
│  │                                                                                                        │  │
│  └────────────────────────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                                               │
└───────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

                    ┌─────────────────────────────────────────────────────────────────────┐
                    │                      Servicios Adicionales GCP                       │
                    │                                                                      │
                    │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────┐ │
                    │  │   Firebase   │  │  Cloud Build │  │  Artifact    │  │ BigQuery │ │
                    │  │   (Push/Auth)│  │   (CI/CD)    │  │  Registry    │  │(Analytics)│ │
                    │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────┘ │
                    │                                                                      │
                    │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────┐ │
                    │  │  Pub/Sub     │  │  Cloud       │  │   SendGrid   │  │  Twilio  │ │
                    │  │  (Events)    │  │  Scheduler   │  │   (Email)    │  │  (SMS)   │ │
                    │  └──────────────┘  └──────────────┘  └──────────────┘  └──────────┘ │
                    │                                                                      │
                    └─────────────────────────────────────────────────────────────────────┘
```

---

## 4. Componentes Detallados

### 4.1 Compute: Cloud Run

Cloud Run es la opción recomendada por su simplicidad y alineación con el estándar Indunnova (menor complejidad operativa).

```yaml
# cloud-run-service.yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: sd-lms-web
  annotations:
    run.googleapis.com/ingress: all
    run.googleapis.com/execution-environment: gen2
spec:
  template:
    metadata:
      annotations:
        autoscaling.knative.dev/minScale: "1"
        autoscaling.knative.dev/maxScale: "10"
        run.googleapis.com/cpu-throttling: "false"
        run.googleapis.com/vpc-access-connector: "sd-lms-connector"
        run.googleapis.com/vpc-access-egress: "private-ranges-only"
    spec:
      containerConcurrency: 80
      timeoutSeconds: 300
      containers:
        - image: southamerica-east1-docker.pkg.dev/sd-lms/app/web:latest
          ports:
            - containerPort: 8000
          resources:
            limits:
              cpu: "2"
              memory: "2Gi"
          env:
            - name: DJANGO_SETTINGS_MODULE
              value: "config.settings.production"
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: database-url
                  key: latest
            - name: REDIS_URL
              valueFrom:
                secretKeyRef:
                  name: redis-url
                  key: latest
```

| Servicio | Configuración | Escalamiento |
|----------|---------------|--------------|
| **sd-lms-web** | 2 vCPU, 2GB RAM | 1-10 instancias |
| **sd-lms-api** | 2 vCPU, 2GB RAM | 1-10 instancias |
| **sd-lms-admin** | 1 vCPU, 1GB RAM | 0-3 instancias |
| **celery-worker** | 2 vCPU, 4GB RAM | 1-5 instancias |
| **media-processor** | 4 vCPU, 8GB RAM | 0-3 (on-demand) |

### 4.2 Base de Datos: Cloud SQL PostgreSQL

```hcl
# terraform/modules/cloudsql/main.tf
resource "google_sql_database_instance" "main" {
  name             = "sd-lms-db"
  database_version = "POSTGRES_16"
  region           = "southamerica-east1"

  settings {
    tier              = "db-custom-2-8192"  # 2 vCPU, 8GB RAM
    availability_type = "REGIONAL"          # High Availability
    disk_type         = "PD_SSD"
    disk_size         = 100
    disk_autoresize   = true

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      start_time                     = "03:00"
      transaction_log_retention_days = 7
      backup_retention_settings {
        retained_backups = 30
      }
    }

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.main.id
    }

    database_flags {
      name  = "max_connections"
      value = "200"
    }

    database_flags {
      name  = "log_checkpoints"
      value = "on"
    }

    insights_config {
      query_insights_enabled  = true
      record_application_tags = true
      record_client_address   = true
    }

    maintenance_window {
      day          = 7  # Sunday
      hour         = 3
      update_track = "stable"
    }
  }

  deletion_protection = true
}

# Connection via Cloud SQL Auth Proxy (recommended)
resource "google_sql_database_instance" "read_replica" {
  name                 = "sd-lms-db-replica"
  master_instance_name = google_sql_database_instance.main.name
  region               = "southamerica-east1"
  database_version     = "POSTGRES_16"

  replica_configuration {
    failover_target = true
  }

  settings {
    tier              = "db-custom-2-8192"
    availability_type = "ZONAL"
    disk_type         = "PD_SSD"
    disk_size         = 100
  }
}
```

| Configuración | Especificación |
|---------------|----------------|
| **Versión** | PostgreSQL 16 |
| **Instancia** | db-custom-2-8192 (2 vCPU, 8GB RAM) |
| **Alta Disponibilidad** | Regional (Multi-zone) |
| **Almacenamiento** | 100GB SSD (auto-resize) |
| **Backups** | Diarios + PITR 7 días |
| **Réplica de lectura** | Sí (para reportes) |

### 4.3 Caché: Memorystore for Redis

```hcl
resource "google_redis_instance" "cache" {
  name           = "sd-lms-redis"
  tier           = "STANDARD_HA"
  memory_size_gb = 5
  region         = "southamerica-east1"

  redis_version  = "REDIS_7_0"

  authorized_network = google_compute_network.main.id
  connect_mode       = "PRIVATE_SERVICE_ACCESS"

  redis_configs = {
    maxmemory-policy = "allkeys-lru"
  }

  maintenance_policy {
    weekly_maintenance_window {
      day = "SUNDAY"
      start_time {
        hours   = 3
        minutes = 0
      }
    }
  }
}
```

| Configuración | Especificación |
|---------------|----------------|
| **Versión** | Redis 7.0 |
| **Tier** | Standard HA (alta disponibilidad) |
| **Memoria** | 5GB |
| **Uso** | Cache, sesiones, Celery broker |

### 4.4 Almacenamiento: Cloud Storage

```hcl
# Bucket para media (videos, PDFs, etc.)
resource "google_storage_bucket" "media" {
  name          = "sd-lms-media-${var.project_id}"
  location      = "SOUTHAMERICA-EAST1"
  storage_class = "STANDARD"

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }

  lifecycle_rule {
    condition {
      age = 365
    }
    action {
      type          = "SetStorageClass"
      storage_class = "COLDLINE"
    }
  }

  cors {
    origin          = ["https://*.sd-lms.com"]
    method          = ["GET", "PUT", "POST"]
    response_header = ["Content-Type", "Content-MD5"]
    max_age_seconds = 3600
  }
}

# Bucket para contenido offline (comprimido)
resource "google_storage_bucket" "offline" {
  name          = "sd-lms-offline-${var.project_id}"
  location      = "SOUTHAMERICA-EAST1"
  storage_class = "STANDARD"

  uniform_bucket_level_access = true
}

# Bucket para backups
resource "google_storage_bucket" "backups" {
  name          = "sd-lms-backups-${var.project_id}"
  location      = "SOUTHAMERICA-EAST1"
  storage_class = "NEARLINE"

  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type          = "SetStorageClass"
      storage_class = "COLDLINE"
    }
  }
}
```

### 4.5 CDN: Cloud CDN

```hcl
resource "google_compute_backend_bucket" "media_cdn" {
  name        = "sd-lms-media-cdn"
  bucket_name = google_storage_bucket.media.name
  enable_cdn  = true

  cdn_policy {
    cache_mode        = "CACHE_ALL_STATIC"
    default_ttl       = 86400      # 1 día
    max_ttl           = 604800     # 7 días
    client_ttl        = 86400
    negative_caching  = true
    serve_while_stale = 86400

    cache_key_policy {
      include_host         = true
      include_protocol     = true
      include_query_string = false
    }
  }
}

resource "google_compute_url_map" "media" {
  name            = "sd-lms-media-urlmap"
  default_service = google_compute_backend_bucket.media_cdn.id

  host_rule {
    hosts        = ["media.sd-lms.com"]
    path_matcher = "media"
  }

  path_matcher {
    name            = "media"
    default_service = google_compute_backend_bucket.media_cdn.id

    path_rule {
      paths   = ["/videos/*"]
      service = google_compute_backend_bucket.media_cdn.id
      route_action {
        cdn_policy {
          default_ttl = 604800  # 7 días para videos
        }
      }
    }
  }
}
```

---

## 5. Seguridad

### 5.1 Cloud Armor (WAF)

```hcl
resource "google_compute_security_policy" "main" {
  name = "sd-lms-security-policy"

  # Regla: Protección OWASP Top 10
  rule {
    action   = "deny(403)"
    priority = "1000"
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('xss-v33-stable')"
      }
    }
    description = "XSS protection"
  }

  rule {
    action   = "deny(403)"
    priority = "1001"
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('sqli-v33-stable')"
      }
    }
    description = "SQL injection protection"
  }

  rule {
    action   = "deny(403)"
    priority = "1002"
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('lfi-v33-stable')"
      }
    }
    description = "Local file inclusion protection"
  }

  # Rate limiting
  rule {
    action   = "throttle"
    priority = "2000"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      rate_limit_threshold {
        count        = 100
        interval_sec = 60
      }
    }
    description = "Rate limiting"
  }

  # Geo-restriction (solo países de operación)
  rule {
    action   = "allow"
    priority = "3000"
    match {
      expr {
        expression = "origin.region_code == 'CO' || origin.region_code == 'EC' || origin.region_code == 'PE' || origin.region_code == 'BR'"
      }
    }
    description = "Allow LATAM countries"
  }

  # Default deny (opcional, ajustar según necesidades)
  rule {
    action   = "allow"
    priority = "2147483647"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    description = "Default rule"
  }
}
```

### 5.2 Identity-Aware Proxy (IAP)

Para proteger el panel de administración:

```hcl
resource "google_iap_web_backend_service_iam_binding" "admin" {
  project             = var.project_id
  web_backend_service = google_compute_backend_service.admin.name
  role                = "roles/iap.httpsResourceAccessor"
  members = [
    "user:admin@sd-sas.com",
    "group:admins@sd-sas.com",
  ]
}
```

### 5.3 Secret Manager

```hcl
resource "google_secret_manager_secret" "database_url" {
  secret_id = "database-url"

  replication {
    user_managed {
      replicas {
        location = "southamerica-east1"
      }
    }
  }
}

resource "google_secret_manager_secret" "django_secret_key" {
  secret_id = "django-secret-key"

  replication {
    user_managed {
      replicas {
        location = "southamerica-east1"
      }
    }
  }
}

# IAM para Cloud Run
resource "google_secret_manager_secret_iam_member" "cloudrun_access" {
  secret_id = google_secret_manager_secret.database_url.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloudrun.email}"
}
```

### 5.4 Seguridad Django (Alineado con Indunnova)

```python
# config/settings/security.py

# django-axes - Protección contra fuerza bruta
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(hours=1)
AXES_LOCKOUT_TEMPLATE = "security/lockout.html"

# django-csp - Content Security Policy
CSP_DEFAULT_SRC = ("'self'",)
CSP_SCRIPT_SRC = ("'self'", "'unsafe-inline'", "htmx.org", "cdn.jsdelivr.net")
CSP_STYLE_SRC = ("'self'", "'unsafe-inline'", "cdn.jsdelivr.net")
CSP_IMG_SRC = ("'self'", "data:", "storage.googleapis.com")
CSP_FONT_SRC = ("'self'", "fonts.gstatic.com")
CSP_CONNECT_SRC = ("'self'", "*.sd-lms.com")

# django-cors-headers
CORS_ALLOWED_ORIGINS = [
    "https://sd-lms.com",
    "https://app.sd-lms.com",
]
CORS_ALLOW_CREDENTIALS = True

# HTTPS y cookies seguras
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
```

---

## 6. Monitoreo y Observabilidad

### 6.1 Stack de Observabilidad GCP + Sentry

```
┌─────────────────────────────────────────────────────────────────┐
│                    OBSERVABILIDAD (GCP + Sentry)                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐    ┌──────────────────┐                   │
│  │  Cloud Logging   │    │  Cloud Monitoring│                   │
│  │                  │    │                  │                   │
│  │  - App logs      │    │  - Métricas      │                   │
│  │  - Access logs   │    │  - Dashboards    │                   │
│  │  - Audit logs    │    │  - Uptime checks │                   │
│  └────────┬─────────┘    └────────┬─────────┘                   │
│           │                       │                              │
│           └───────────┬───────────┘                              │
│                       │                                          │
│           ┌───────────▼───────────┐                              │
│           │    Cloud Alerting     │                              │
│           │                       │                              │
│           │  - PagerDuty          │                              │
│           │  - Slack              │                              │
│           │  - Email              │                              │
│           └───────────────────────┘                              │
│                                                                  │
│  ┌──────────────────┐    ┌──────────────────┐                   │
│  │     Sentry       │    │   Cloud Trace    │                   │
│  │  (Error Track)   │    │  (Distributed)   │                   │
│  │                  │    │                  │                   │
│  │  - Exceptions    │    │  - Request trace │                   │
│  │  - Performance   │    │  - Latency       │                   │
│  │  - Release track │    │  - Dependencies  │                   │
│  └──────────────────┘    └──────────────────┘                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 Configuración de Alertas

```hcl
resource "google_monitoring_alert_policy" "high_error_rate" {
  display_name = "High Error Rate"
  combiner     = "OR"

  conditions {
    display_name = "5xx errors > 1%"
    condition_threshold {
      filter          = "resource.type = \"cloud_run_revision\" AND metric.type = \"run.googleapis.com/request_count\" AND metric.labels.response_code_class = \"5xx\""
      duration        = "60s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.01
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  notification_channels = [
    google_monitoring_notification_channel.slack.name,
    google_monitoring_notification_channel.pagerduty.name,
  ]

  alert_strategy {
    auto_close = "1800s"
  }
}

resource "google_monitoring_alert_policy" "high_latency" {
  display_name = "High Latency"
  combiner     = "OR"

  conditions {
    display_name = "P95 latency > 2s"
    condition_threshold {
      filter          = "resource.type = \"cloud_run_revision\" AND metric.type = \"run.googleapis.com/request_latencies\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 2000  # 2 seconds
      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_PERCENTILE_95"
        cross_series_reducer = "REDUCE_MEAN"
      }
    }
  }

  notification_channels = [
    google_monitoring_notification_channel.slack.name,
  ]
}

resource "google_monitoring_alert_policy" "database_connections" {
  display_name = "Database Connections High"
  combiner     = "OR"

  conditions {
    display_name = "Connections > 80%"
    condition_threshold {
      filter          = "resource.type = \"cloudsql_database\" AND metric.type = \"cloudsql.googleapis.com/database/postgresql/num_backends\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 160  # 80% of 200
    }
  }

  notification_channels = [
    google_monitoring_notification_channel.pagerduty.name,
  ]
}
```

### 6.3 Dashboard Personalizado

```hcl
resource "google_monitoring_dashboard" "main" {
  dashboard_json = jsonencode({
    displayName = "SD LMS - Overview"
    gridLayout = {
      widgets = [
        {
          title = "Request Rate"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "resource.type=\"cloud_run_revision\" metric.type=\"run.googleapis.com/request_count\""
                }
              }
            }]
          }
        },
        {
          title = "Error Rate"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "resource.type=\"cloud_run_revision\" metric.type=\"run.googleapis.com/request_count\" metric.labels.response_code_class=\"5xx\""
                }
              }
            }]
          }
        },
        {
          title = "Database CPU"
          xyChart = {
            dataSets = [{
              timeSeriesQuery = {
                timeSeriesFilter = {
                  filter = "resource.type=\"cloudsql_database\" metric.type=\"cloudsql.googleapis.com/database/cpu/utilization\""
                }
              }
            }]
          }
        },
        {
          title = "Active Users"
          scorecard = {
            timeSeriesQuery = {
              timeSeriesFilter = {
                filter = "metric.type=\"custom.googleapis.com/sd_lms/active_users\""
              }
            }
          }
        }
      ]
    }
  })
}
```

---

## 7. CI/CD Pipeline

### 7.1 Cloud Build + GitHub Actions

```yaml
# cloudbuild.yaml
steps:
  # Run tests
  - name: 'python:3.12-slim'
    entrypoint: 'bash'
    args:
      - '-c'
      - |
        pip install -r requirements/test.txt
        pytest --cov=apps --cov-report=xml --cov-fail-under=80
    env:
      - 'DJANGO_SETTINGS_MODULE=config.settings.test'
      - 'DATABASE_URL=sqlite:///test.db'

  # Lint with Ruff
  - name: 'python:3.12-slim'
    entrypoint: 'bash'
    args:
      - '-c'
      - |
        pip install ruff
        ruff check .
        ruff format --check .

  # Type check with mypy
  - name: 'python:3.12-slim'
    entrypoint: 'bash'
    args:
      - '-c'
      - |
        pip install mypy django-stubs
        mypy apps/

  # Build Docker image
  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'build'
      - '-t'
      - 'southamerica-east1-docker.pkg.dev/$PROJECT_ID/sd-lms/web:$COMMIT_SHA'
      - '-t'
      - 'southamerica-east1-docker.pkg.dev/$PROJECT_ID/sd-lms/web:latest'
      - '-f'
      - 'docker/Dockerfile.web'
      - '.'

  # Push to Artifact Registry
  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'push'
      - 'southamerica-east1-docker.pkg.dev/$PROJECT_ID/sd-lms/web:$COMMIT_SHA'

  - name: 'gcr.io/cloud-builders/docker'
    args:
      - 'push'
      - 'southamerica-east1-docker.pkg.dev/$PROJECT_ID/sd-lms/web:latest'

  # Deploy to Cloud Run (Staging)
  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
    entrypoint: 'gcloud'
    args:
      - 'run'
      - 'deploy'
      - 'sd-lms-web-staging'
      - '--image=southamerica-east1-docker.pkg.dev/$PROJECT_ID/sd-lms/web:$COMMIT_SHA'
      - '--region=southamerica-east1'
      - '--platform=managed'
      - '--allow-unauthenticated'
      - '--set-env-vars=DJANGO_SETTINGS_MODULE=config.settings.staging'

  # Run Django migrations
  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
    entrypoint: 'gcloud'
    args:
      - 'run'
      - 'jobs'
      - 'execute'
      - 'sd-lms-migrate'
      - '--region=southamerica-east1'
      - '--wait'

options:
  logging: CLOUD_LOGGING_ONLY

substitutions:
  _DEPLOY_ENV: staging

images:
  - 'southamerica-east1-docker.pkg.dev/$PROJECT_ID/sd-lms/web:$COMMIT_SHA'
  - 'southamerica-east1-docker.pkg.dev/$PROJECT_ID/sd-lms/web:latest'
```

### 7.2 GitHub Actions para PRs

```yaml
# .github/workflows/ci.yml
name: CI

on:
  pull_request:
    branches: [main, develop]
  push:
    branches: [main, develop]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: test
          POSTGRES_DB: test_db
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      redis:
        image: redis:7
        ports:
          - 6379:6379

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'

      - name: Install dependencies
        run: |
          pip install -r requirements/dev.txt

      - name: Run Ruff linter
        run: ruff check .

      - name: Run Ruff formatter
        run: ruff format --check .

      - name: Run mypy
        run: mypy apps/

      - name: Run tests
        env:
          DATABASE_URL: postgres://postgres:test@localhost:5432/test_db
          REDIS_URL: redis://localhost:6379/0
          DJANGO_SETTINGS_MODULE: config.settings.test
        run: |
          pytest --cov=apps --cov-report=xml --cov-fail-under=80

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml

  trigger-cloud-build:
    needs: test
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - id: auth
        uses: google-github-actions/auth@v2
        with:
          credentials_json: ${{ secrets.GCP_SA_KEY }}

      - name: Set up Cloud SDK
        uses: google-github-actions/setup-gcloud@v2

      - name: Trigger Cloud Build
        run: |
          gcloud builds submit --config=cloudbuild.yaml .
```

---

## 8. Disaster Recovery

### 8.1 Estrategia de Backup

| Componente | Estrategia | RPO | Retención |
|------------|------------|-----|-----------|
| **Cloud SQL** | Backups automáticos diarios | 1 hora (PITR) | 30 días |
| **Cloud SQL** | Point-in-Time Recovery | 5 minutos | 7 días |
| **Cloud Storage** | Versionamiento | Inmediato | 90 días |
| **Cloud Storage** | Cross-region replication | Inmediato | Indefinido |
| **Secrets** | Replicación automática | Inmediato | - |

### 8.2 Plan de Recuperación

```
┌─────────────────────────────────────────────────────────────────┐
│                    DISASTER RECOVERY PLAN                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Nivel 1: Falla de Servicio (RTO: 1 min)                        │
│  ├── Cloud Run auto-restart                                      │
│  ├── Health checks automáticos                                   │
│  └── Load balancer failover                                      │
│                                                                  │
│  Nivel 2: Falla de Zona (RTO: 5 min)                            │
│  ├── Cloud SQL failover automático                               │
│  ├── Cloud Run multi-zone                                        │
│  └── Memorystore HA replica                                      │
│                                                                  │
│  Nivel 3: Falla de Región (RTO: 4 horas)                        │
│  ├── Activar stack en región secundaria (us-east1)              │
│  ├── Restore Cloud SQL desde backup                              │
│  ├── DNS failover manual                                         │
│  └── Notificación a usuarios                                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 8.3 Runbook de Recuperación de Base de Datos

```bash
#!/bin/bash
# Runbook: Recuperación de Cloud SQL
# Tiempo estimado: 30-60 minutos

# 1. Listar backups disponibles
gcloud sql backups list --instance=sd-lms-db

# 2. Restaurar desde backup específico
gcloud sql backups restore BACKUP_ID \
  --restore-instance=sd-lms-db-restored \
  --backup-instance=sd-lms-db

# 3. Verificar estado de la instancia restaurada
gcloud sql instances describe sd-lms-db-restored

# 4. Actualizar secreto con nuevo endpoint
gcloud secrets versions add database-url \
  --data-file=- <<< "postgres://user:pass@NEW_IP:5432/sdlms"

# 5. Forzar nuevo deployment para reconectar
gcloud run services update sd-lms-web \
  --region=southamerica-east1 \
  --update-env-vars=DB_RECONNECT=$(date +%s)
```

---

## 9. Estimación de Costos GCP

### 9.1 Costos Mensuales Estimados (USD)

| Servicio | Configuración | Costo Estimado/Mes |
|----------|---------------|-------------------|
| **Cloud Run (Web)** | 2 vCPU, 2GB, min 1 instancia | $50 |
| **Cloud Run (API)** | 2 vCPU, 2GB, min 1 instancia | $50 |
| **Cloud Run (Workers)** | 2 vCPU, 4GB, on-demand | $30 |
| **Cloud Run (Jobs)** | Media processing, on-demand | $20 |
| **Cloud SQL PostgreSQL** | db-custom-2-8192, HA | $200 |
| **Cloud SQL (Replica)** | db-custom-2-8192 | $100 |
| **Memorystore Redis** | Standard HA, 5GB | $175 |
| **Cloud Storage** | 500GB Standard + transfers | $25 |
| **Cloud CDN** | 1TB egress | $80 |
| **Cloud Load Balancer** | 1 forwarding rule | $20 |
| **Cloud Armor** | Security policy | $10 |
| **Cloud DNS** | Hosted zone + queries | $5 |
| **Secret Manager** | 10 secrets | $0.60 |
| **Cloud Logging** | 10GB/month | $5 |
| **Cloud Monitoring** | Métricas + alertas | $10 |
| **Cloud Build** | 120 min/día | $0 (free tier) |
| **Artifact Registry** | 10GB images | $1 |
| **SendGrid** | 10K emails | $15 |
| **Firebase (Push)** | Notifications | $0 (free tier) |
| **Networking** | VPC, egress | $30 |

### 9.2 Resumen de Costos

| Concepto | Costo Mensual | Costo Anual |
|----------|---------------|-------------|
| **Infraestructura Base** | ~$827 | ~$9,924 |
| **Committed Use (1 año, -20%)** | ~$662 | ~$7,939 |
| **Soporte Standard** | ~$100 | ~$1,200 |
| **Total Estimado** | ~$762 | ~$9,139 |

### 9.3 Comparativa AWS vs GCP

| Concepto | AWS (Mensual) | GCP (Mensual) | Ahorro |
|----------|---------------|---------------|--------|
| **Compute** | $253 (EKS + EC2) | $150 (Cloud Run) | 41% |
| **Database** | $290 (RDS) | $200 (Cloud SQL) | 31% |
| **Cache** | $240 (ElastiCache) | $175 (Memorystore) | 27% |
| **CDN** | $85 (CloudFront) | $80 (Cloud CDN) | 6% |
| **Total** | ~$1,134 | ~$827 | **27%** |

**Nota:** GCP ofrece mejor precio principalmente por:
- Cloud Run (serverless, pago por uso real)
- Descuentos por uso sostenido automáticos
- Precios competitivos en LATAM

---

## 10. Comparativa con Estándar Indunnova

### 10.1 Alineación por Componente

| Componente | Estándar Indunnova | Implementación SD LMS | Estado |
|------------|-------------------|----------------------|--------|
| **Python** | 3.12.x / 3.13.x | 3.12.x | ✅ Alineado |
| **Django** | 5.1.x LTS | 5.1 LTS | ✅ Alineado |
| **PostgreSQL** | 16.x / 17.x | 16 (Cloud SQL) | ✅ Alineado |
| **Redis** | 7.x | 7.0 (Memorystore) | ✅ Alineado |
| **DRF** | 3.15+ | 3.15 | ✅ Alineado |
| **Django Ninja** | Para APIs alto rendimiento | Sí | ✅ Alineado |
| **Celery** | Con Redis broker | Cloud Tasks + Celery | ✅ Alineado |
| **Frontend Web** | HTMX + Alpine.js + Tailwind | HTMX + Alpine.js + Tailwind | ✅ Alineado |
| **Seguridad** | django-axes, django-csp, 2FA | Implementado | ✅ Alineado |
| **Testing** | pytest, factory_boy, 80% cov | Configurado | ✅ Alineado |
| **Linting** | Ruff, mypy, pre-commit | Configurado | ✅ Alineado |
| **Monitoreo** | Sentry + Prometheus/Grafana | Sentry + Cloud Monitoring | ✅ Alineado |
| **Cloud** | DigitalOcean / AWS / GCP | GCP (Cloud Run) | ✅ Alineado |
| **CI/CD** | GitHub Actions | GitHub Actions + Cloud Build | ✅ Alineado |

### 10.2 Excepciones Justificadas

| Componente | Estándar | SD LMS | Justificación |
|------------|----------|--------|---------------|
| **App Móvil** | No especificado | React Native | Requerimiento de modo offline robusto |
| **GraphQL** | Strawberry | No incluido inicialmente | Se puede agregar en fase posterior |
| **pgBouncer** | Recomendado | No requerido | Cloud SQL maneja connection pooling |
| **MinIO** | Para archivos | Cloud Storage | Servicio gestionado GCP |

---

## 11. Checklist de Implementación GCP

### Fase 0: Setup Inicial

- [ ] Crear proyecto GCP y habilitar billing
- [ ] Configurar Organization y folders
- [ ] Habilitar APIs necesarias (Cloud Run, SQL, etc.)
- [ ] Crear Service Accounts con IAM apropiado
- [ ] Configurar VPC y Serverless VPC Connector
- [ ] Crear repositorio Terraform
- [ ] Configurar Cloud DNS y dominios
- [ ] Crear Artifact Registry para imágenes

### Fase 1: Base de Datos y Caché

- [ ] Desplegar Cloud SQL PostgreSQL
- [ ] Configurar alta disponibilidad y backups
- [ ] Desplegar Memorystore Redis
- [ ] Configurar Secret Manager con credenciales
- [ ] Ejecutar migraciones iniciales de Django

### Fase 2: Compute y Storage

- [ ] Crear buckets Cloud Storage
- [ ] Configurar Cloud CDN
- [ ] Desplegar servicios Cloud Run (web, api, workers)
- [ ] Configurar Cloud Tasks para Celery
- [ ] Configurar Cloud Scheduler para tareas periódicas

### Fase 3: Seguridad y Redes

- [ ] Configurar Cloud Armor (WAF)
- [ ] Configurar IAP para admin
- [ ] Configurar SSL/TLS con certificados gestionados
- [ ] Revisar y ajustar IAM permissions
- [ ] Habilitar Cloud Audit Logs

### Fase 4: CI/CD y Monitoreo

- [ ] Configurar Cloud Build triggers
- [ ] Configurar GitHub Actions integration
- [ ] Crear dashboards en Cloud Monitoring
- [ ] Configurar alertas críticas
- [ ] Integrar Sentry para error tracking
- [ ] Configurar Uptime checks

### Fase 5: Deploy y Verificación

- [ ] Deploy ambiente staging
- [ ] Ejecutar pruebas E2E
- [ ] Pruebas de carga (k6)
- [ ] Deploy ambiente production
- [ ] Verificar disaster recovery
- [ ] Documentar runbooks

---

*Documento de arquitectura de infraestructura GCP para el Sistema LMS de S.D. S.A.S., alineado con el Estándar de Infraestructura Tecnológica de Indunnova SAS v2.0*
