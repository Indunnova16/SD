# Arquitectura del Sistema - SD LMS

Documentacion de la arquitectura del Sistema LMS de S.D. S.A.S., incluyendo patrones de diseno, estructura de componentes y flujos de datos.

## Tabla de Contenidos

- [Vision General](#vision-general)
- [Diagrama de Componentes](#diagrama-de-componentes)
- [Patrones de Diseno](#patrones-de-diseno)
- [Estructura de Apps Django](#estructura-de-apps-django)
- [Flujo de Datos](#flujo-de-datos)
- [Integraciones Externas](#integraciones-externas)

---

## Vision General

El Sistema LMS de S.D. S.A.S. es una plataforma de gestion del aprendizaje disenada para garantizar que el personal que opera en lineas de transmision electrica cuente con las competencias necesarias para ejecutar trabajos de alto riesgo de manera segura.

### Principios de Arquitectura

1. **Modularidad**: Cada dominio de negocio esta encapsulado en una app Django independiente
2. **Separacion de Responsabilidades**: Uso de capas (Models, Services, Views, API)
3. **Offline-First**: Soporte para operacion sin conectividad
4. **Seguridad**: Multiples capas de proteccion (WAF, autenticacion, autorizacion)
5. **Escalabilidad**: Arquitectura serverless con Cloud Run

### Stack Tecnologico

| Capa | Tecnologia |
|------|------------|
| **Backend** | Python 3.12, Django 5.1 LTS |
| **API** | Django REST Framework, Django Ninja |
| **Base de Datos** | PostgreSQL 16 (Cloud SQL) |
| **Cache** | Redis 7.x (Memorystore) |
| **Tareas Async** | Celery + Redis |
| **Frontend Web** | HTMX 2.x, Alpine.js 3.x, Tailwind CSS |
| **Frontend Movil** | React Native + Expo |
| **Infraestructura** | Google Cloud Platform |

---

## Diagrama de Componentes

```
+--------------------------------------------------------------------------------------------------+
|                                         CLIENTES                                                  |
|                                                                                                  |
|    +------------------+     +------------------+     +------------------+                        |
|    |   Navegador Web  |     |   App Movil      |     |   Sistemas       |                        |
|    |   (HTMX/Alpine)  |     |   (React Native) |     |   Externos       |                        |
|    +--------+---------+     +--------+---------+     +--------+---------+                        |
|             |                        |                        |                                  |
+-------------|------------------------|------------------------|----------------------------------+
              |                        |                        |
              v                        v                        v
+--------------------------------------------------------------------------------------------------+
|                                    CAPA DE ENTRADA                                               |
|                                                                                                  |
|    +------------------+     +------------------+     +------------------+                        |
|    |   Cloud CDN      |     |  Cloud Load      |     |   Cloud Armor    |                        |
|    |   (Static/Media) |     |  Balancer (L7)   |     |   (WAF)          |                        |
|    +--------+---------+     +--------+---------+     +--------+---------+                        |
|             |                        |                        |                                  |
+-------------|------------------------|------------------------|----------------------------------+
              |                        |                        |
              v                        v                        v
+--------------------------------------------------------------------------------------------------+
|                                CAPA DE APLICACION (Cloud Run)                                    |
|                                                                                                  |
|    +------------------+     +------------------+     +------------------+                        |
|    |   Django Web     |     |   Django API     |     |   Django Admin   |                        |
|    |   (HTMX Views)   |     |   (DRF + Ninja)  |     |   (Back-office)  |                        |
|    +--------+---------+     +--------+---------+     +--------+---------+                        |
|             |                        |                        |                                  |
|    +--------+------------------------+------------------------+---------+                        |
|    |                                                                    |                        |
|    |                         SERVICE LAYER                              |                        |
|    |                                                                    |                        |
|    |    +-------------+  +-------------+  +-------------+               |                        |
|    |    | Certificate |  | Assessment  |  | Enrollment  |               |                        |
|    |    | Service     |  | Service     |  | Service     |   ...         |                        |
|    |    +-------------+  +-------------+  +-------------+               |                        |
|    |                                                                    |                        |
|    +--------------------------------------------------------------------+                        |
|                                                                                                  |
+--------------------------------------------------------------------------------------------------+
              |                        |                        |
              v                        v                        v
+--------------------------------------------------------------------------------------------------+
|                                   CAPA DE WORKERS                                                |
|                                                                                                  |
|    +------------------+     +------------------+     +------------------+                        |
|    |   Celery Worker  |     |   Celery Beat    |     |   Cloud Tasks    |                        |
|    |   (Background)   |     |   (Scheduler)    |     |   (Triggers)     |                        |
|    +--------+---------+     +--------+---------+     +--------+---------+                        |
|             |                        |                        |                                  |
+-------------|------------------------|------------------------|----------------------------------+
              |                        |                        |
              v                        v                        v
+--------------------------------------------------------------------------------------------------+
|                                    CAPA DE DATOS                                                 |
|                                                                                                  |
|    +------------------+     +------------------+     +------------------+                        |
|    |   Cloud SQL      |     |   Memorystore    |     |   Cloud Storage  |                        |
|    |   PostgreSQL 16  |     |   Redis 7.x      |     |   (Media/Files)  |                        |
|    +------------------+     +------------------+     +------------------+                        |
|                                                                                                  |
+--------------------------------------------------------------------------------------------------+
              |                        |                        |
              v                        v                        v
+--------------------------------------------------------------------------------------------------+
|                              SERVICIOS DE SOPORTE                                                |
|                                                                                                  |
|    +------------------+     +------------------+     +------------------+                        |
|    |   Secret Manager |     |   Cloud Logging  |     |   Cloud Monitor  |                        |
|    |   (Credentials)  |     |   (Logs)         |     |   (Metrics)      |                        |
|    +------------------+     +------------------+     +------------------+                        |
|                                                                                                  |
|    +------------------+     +------------------+     +------------------+                        |
|    |   Sentry         |     |   Firebase       |     |   BigQuery       |                        |
|    |   (Errors)       |     |   (Push Notif)   |     |   (Analytics)    |                        |
|    +------------------+     +------------------+     +------------------+                        |
|                                                                                                  |
+--------------------------------------------------------------------------------------------------+
```

---

## Patrones de Diseno

### Service Layer Pattern

Toda la logica de negocio se encapsula en servicios, separando las responsabilidades de los modelos y las vistas.

```
+----------------+     +----------------+     +----------------+
|     Views      | --> |    Services    | --> |     Models     |
|   (API/HTMX)   |     |  (Business)    |     |   (Data)       |
+----------------+     +----------------+     +----------------+
        |                      |                      |
        |                      |                      |
        v                      v                      v
   Presentacion          Logica de           Acceso a Datos
                         Negocio
```

#### Ejemplo de Service

```python
# apps/certifications/services.py

class CertificateService:
    """Servicio para operaciones de certificados."""

    @staticmethod
    def can_issue_certificate(user, course: Course) -> dict:
        """Verifica si se puede emitir un certificado."""
        # Validaciones de negocio
        ...

    @staticmethod
    @transaction.atomic
    def issue_certificate(user, course: Course, ...) -> Certificate:
        """Emite un certificado para un usuario."""
        # Logica de negocio
        check = CertificateService.can_issue_certificate(user, course)
        if not check["can_issue"]:
            raise ValueError(check["reason"])

        # Crear certificado
        certificate = Certificate.objects.create(...)

        # Generar PDF y QR
        CertificateService.generate_certificate_file(certificate)

        return certificate

    @staticmethod
    def verify_certificate(certificate_number: str, ...) -> dict:
        """Verifica un certificado por su numero."""
        ...
```

### Ventajas del Service Layer

1. **Reutilizacion**: La misma logica se usa en Views, API y Celery tasks
2. **Testabilidad**: Facil de probar sin dependencias de HTTP
3. **Transacciones**: Control explicito de transacciones
4. **Desacoplamiento**: Los modelos permanecen simples

### Modelo Base Abstracto

Todos los modelos heredan de clases base que proporcionan funcionalidad comun.

```python
# apps/core/models.py

class BaseModel(models.Model):
    """Modelo base con timestamps."""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteModel(BaseModel):
    """Modelo con borrado logico."""
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        abstract = True

    def delete(self, ...):
        """Borrado logico."""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save()


class OrderedModel(BaseModel):
    """Modelo con ordenamiento."""
    order = models.PositiveIntegerField(default=0)

    class Meta:
        abstract = True
        ordering = ["order"]
```

### ViewSet Pattern (DRF)

Las APIs REST utilizan ViewSets para operaciones CRUD estandar.

```python
# apps/courses/api/views.py


class CourseViewSet(viewsets.ModelViewSet):
    """API ViewSet para cursos."""

    queryset = Course.objects.all()
    serializer_class = CourseSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["category", "status", "is_mandatory"]
    search_fields = ["title", "description"]
    ordering_fields = ["title", "created_at"]

    def get_queryset(self):
        """Filtra queryset segun permisos del usuario."""
        qs = super().get_queryset()
        if not self.request.user.is_staff:
            qs = qs.filter(status="published")
        return qs.select_related("category").prefetch_related("modules")

    @action(detail=True, methods=["post"])
    def enroll(self, request, pk=None):
        """Accion personalizada para inscribir usuario."""
        course = self.get_object()
        enrollment = EnrollmentService.enroll_user(request.user, course)
        return Response(EnrollmentSerializer(enrollment).data)
```

### Signals para Eventos

Los signals de Django se usan para desacoplar acciones secundarias.

```python
# apps/gamification/signals.py


@receiver(post_save, sender=Enrollment)
def award_enrollment_points(sender, instance, created, **kwargs):
    """Otorga puntos cuando el usuario se inscribe en un curso."""
    if created:
        GamificationService.award_points(
            user=instance.user,
            action="course_enrollment",
            points=10,
        )
```

---

## Estructura de Apps Django

### Organizacion del Proyecto

```
sd-lms/
|
+-- apps/                          # Aplicaciones Django
|   |
|   +-- accounts/                  # Usuarios y autenticacion
|   |   +-- api/                   # API REST
|   |   |   +-- serializers.py
|   |   |   +-- urls.py
|   |   |   +-- views.py
|   |   +-- tests/                 # Tests
|   |   |   +-- test_api.py
|   |   |   +-- test_views.py
|   |   +-- admin.py               # Django Admin
|   |   +-- apps.py                # App config
|   |   +-- forms.py               # Formularios
|   |   +-- models.py              # Modelos
|   |   +-- signals.py             # Signals
|   |   +-- urls.py                # URLs web
|   |   +-- views.py               # Vistas web
|   |
|   +-- assessments/               # Evaluaciones
|   +-- certifications/            # Certificados
|   +-- core/                      # Utilidades compartidas
|   +-- courses/                   # Gestion de cursos
|   +-- gamification/              # Sistema de puntos e insignias
|   +-- integrations/              # Integraciones externas
|   +-- learning_paths/            # Rutas de aprendizaje
|   +-- lessons_learned/           # Lecciones aprendidas
|   +-- notifications/             # Sistema de notificaciones
|   +-- preop_talks/               # Charlas pre-operacionales
|   +-- reports/                   # Reportes y analitica
|   +-- sync/                      # Sincronizacion offline
|
+-- config/                        # Configuracion Django
|   +-- settings/
|   |   +-- base.py                # Configuracion base
|   |   +-- local.py               # Desarrollo local
|   |   +-- staging.py             # Staging
|   |   +-- production.py          # Produccion
|   |   +-- test.py                # Tests
|   +-- urls.py                    # URLs principales
|   +-- celery.py                  # Configuracion Celery
|   +-- wsgi.py
|   +-- asgi.py
|
+-- templates/                     # Templates Django
|   +-- base.html
|   +-- components/                # Componentes reutilizables
|   +-- accounts/
|   +-- courses/
|   ...
|
+-- static/                        # Archivos estaticos
|   +-- css/
|   +-- js/
|   +-- images/
|
+-- requirements/                  # Dependencias Python
|   +-- base.txt
|   +-- local.txt
|   +-- production.txt
|   +-- test.txt
|
+-- docs/                          # Documentacion
+-- infrastructure/                # IaC (Terraform, Docker)
+-- mobile/                        # Aplicacion React Native
```

### Descripcion de Apps

| App | Responsabilidad |
|-----|-----------------|
| **accounts** | Gestion de usuarios, autenticacion JWT, roles y permisos |
| **courses** | LCMS: cursos, modulos, lecciones, contenido multimedia, SCORM |
| **assessments** | Evaluaciones teoricas y practicas, banco de preguntas |
| **certifications** | Emision, verificacion y gestion de certificados digitales |
| **learning_paths** | Rutas de aprendizaje con prerrequisitos y secuenciacion |
| **lessons_learned** | Repositorio de lecciones aprendidas, micro-learning |
| **preop_talks** | Charlas pre-operacionales con geolocalizacion y firma |
| **gamification** | Puntos, insignias, rankings y motivacion |
| **notifications** | Notificaciones email, push, in-app |
| **reports** | Dashboards, reportes PDF, exportacion |
| **sync** | Sincronizacion offline para app movil |
| **integrations** | Webhooks, APIs externas (SAP, BPM) |
| **core** | Modelos base, utilidades, mixins |

### Dependencias entre Apps

```
                              +-------------+
                              |    core     |
                              +------+------+
                                     |
          +--------------------------+-------------------------+
          |                          |                         |
          v                          v                         v
    +------------+            +------------+            +------------+
    |  accounts  |            |  courses   |<-----------|assessments |
    +-----+------+            +-----+------+            +-----+------+
          |                         |                         |
          |     +-------------------+                         |
          |     |                                             |
          v     v                                             v
    +------------+            +------------+            +------------+
    |  learning  |            |certifica-  |            | gamification|
    |   paths    |----------->|   tions    |            |            |
    +------------+            +------------+            +------------+
          |                         |
          |                         |
          v                         v
    +------------+            +------------+            +------------+
    |notifications|           |  reports   |            |   sync     |
    +------------+            +------------+            +------------+
```

---

## Flujo de Datos

### Flujo de Inscripcion a Curso

```
Usuario                   Frontend                   Backend                    Base de Datos
   |                         |                          |                            |
   | 1. Click "Inscribirse"  |                          |                            |
   |------------------------>|                          |                            |
   |                         | 2. POST /api/courses/1/  |                            |
   |                         |    enroll/               |                            |
   |                         |------------------------->|                            |
   |                         |                          | 3. Validar prerrequisitos  |
   |                         |                          |--------------------------->|
   |                         |                          |<---------------------------|
   |                         |                          |                            |
   |                         |                          | 4. Crear Enrollment        |
   |                         |                          |--------------------------->|
   |                         |                          |<---------------------------|
   |                         |                          |                            |
   |                         |                          | 5. Signal: award_points    |
   |                         |                          |----------+                 |
   |                         |                          |          |                 |
   |                         |                          |<---------+                 |
   |                         |                          |                            |
   |                         |                          | 6. Celery: send_email      |
   |                         |                          |----------> (async)         |
   |                         |                          |                            |
   |                         | 7. Response 201          |                            |
   |                         |<-------------------------|                            |
   | 8. Mostrar confirmacion |                          |                            |
   |<------------------------|                          |                            |
```

### Flujo de Emision de Certificado

```
+-------------+     +-------------+     +-------------+     +-------------+
| Completar   | --> | Trigger     | --> | Certificate | --> | Generate    |
| Curso       |     | Celery Task |     | Service     |     | PDF/QR      |
+-------------+     +-------------+     +-------------+     +-------------+
                                              |
                                              v
                          +-------------------+-------------------+
                          |                                       |
                          v                                       v
                    +-------------+                         +-------------+
                    | Cloud       |                         | Notification|
                    | Storage     |                         | Service     |
                    +-------------+                         +-------------+
                          |                                       |
                          v                                       v
                    +-------------+                         +-------------+
                    | CDN URL     |                         | Email/Push  |
                    +-------------+                         +-------------+
```

### Flujo de Sincronizacion Offline

```
App Movil                   Sync Service                   Backend
    |                            |                            |
    | 1. Detectar conexion       |                            |
    |--------------------------->|                            |
    |                            | 2. GET /api/sync/changes   |
    |                            |    ?since=timestamp        |
    |                            |--------------------------->|
    |                            |                            |
    |                            | 3. Cambios del servidor    |
    |                            |<---------------------------|
    |                            |                            |
    | 4. Aplicar cambios locales |                            |
    |<---------------------------|                            |
    |                            |                            |
    | 5. Enviar cambios locales  |                            |
    |--------------------------->|                            |
    |                            | 6. POST /api/sync/push     |
    |                            |--------------------------->|
    |                            |                            |
    |                            | 7. Resolver conflictos     |
    |                            |<---------------------------|
    |                            |                            |
    | 8. Confirmar sync          |                            |
    |<---------------------------|                            |
```

---

## Integraciones Externas

### Diagrama de Integraciones

```
+--------------------------------------------------------------------------------------------------+
|                                         SD LMS                                                   |
|                                                                                                  |
|    +------------------+     +------------------+     +------------------+                        |
|    |   Integration    |     |    Webhook       |     |    Scheduler     |                        |
|    |   Service        |     |    Handler       |     |    (Celery Beat) |                        |
|    +--------+---------+     +--------+---------+     +--------+---------+                        |
|             |                        |                        |                                  |
+-------------|------------------------|------------------------|----------------------------------+
              |                        |                        |
              v                        v                        v
+--------------------------------------------------------------------------------------------------+
|                                  SERVICIOS EXTERNOS                                              |
|                                                                                                  |
|    +------------------+     +------------------+     +------------------+                        |
|    |    SendGrid      |     |    Firebase      |     |    Twilio        |                        |
|    |    (Email)       |     |    (Push Notif)  |     |    (SMS)         |                        |
|    +------------------+     +------------------+     +------------------+                        |
|                                                                                                  |
|    +------------------+     +------------------+     +------------------+                        |
|    |    Sentry        |     |    Google Maps   |     |    SAP           |                        |
|    |    (Errors)      |     |    (Geolocation) |     |    (ERP)         |                        |
|    +------------------+     +------------------+     +------------------+                        |
|                                                                                                  |
|    +------------------+     +------------------+     +------------------+                        |
|    |    AWS S3        |     |    SCORM Cloud   |     |    BPM System    |                        |
|    |    (Backup Alt)  |     |    (LRS)         |     |    (Workflows)   |                        |
|    +------------------+     +------------------+     +------------------+                        |
|                                                                                                  |
+--------------------------------------------------------------------------------------------------+
```

### Integraciones Implementadas

| Servicio | Proposito | Patron |
|----------|-----------|--------|
| **SendGrid** | Emails transaccionales y notificaciones | API REST |
| **Firebase** | Push notifications para app movil | FCM SDK |
| **Twilio** | SMS para alertas criticas | API REST |
| **Sentry** | Monitoreo de errores y performance | SDK |
| **Google Maps** | Geolocalizacion en charlas pre-op | JavaScript API |

### Ejemplo de Integracion

```python
# apps/integrations/services.py


class SendGridService:
    """Servicio para envio de emails via SendGrid."""

    @staticmethod
    def send_email(
        to: str,
        subject: str,
        template_id: str,
        dynamic_data: dict = None,
    ) -> bool:
        """Envia un email usando SendGrid."""
        try:
            message = Mail(
                from_email=settings.DEFAULT_FROM_EMAIL,
                to_emails=to,
            )
            message.template_id = template_id
            if dynamic_data:
                message.dynamic_template_data = dynamic_data

            sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
            response = sg.send(message)

            return response.status_code in [200, 202]
        except Exception as e:
            logger.exception(f"Error enviando email: {e}")
            return False
```

### Webhooks Entrantes

```python
# apps/integrations/api/views.py


class WebhookView(APIView):
    """Endpoint para recibir webhooks externos."""

    permission_classes = [AllowAny]

    def post(self, request, source):
        """Procesa webhook entrante."""
        # Verificar firma
        if not self._verify_signature(request, source):
            return Response(status=403)

        # Procesar asincrono
        process_webhook.delay(source, request.data)

        return Response({"status": "received"}, status=202)

    def _verify_signature(self, request, source):
        """Verifica la firma del webhook."""
        signature = request.headers.get("X-Webhook-Signature")
        secret = settings.WEBHOOK_SECRETS.get(source)

        if not secret:
            return False

        expected = hmac.new(
            secret.encode(),
            request.body,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(signature, expected)
```

---

## Consideraciones de Seguridad

### Capas de Seguridad

```
1. Cloud Armor (WAF)
   |
   +-> Proteccion DDoS
   +-> Reglas OWASP
   +-> Rate limiting
   +-> Geo-restriction

2. HTTPS/TLS
   |
   +-> Certificados gestionados
   +-> HSTS habilitado

3. Autenticacion
   |
   +-> JWT con refresh tokens
   +-> 2FA opcional
   +-> django-axes (brute force)

4. Autorizacion
   |
   +-> Roles y permisos granulares
   +-> Object-level permissions

5. Validacion de Datos
   |
   +-> Serializers DRF
   +-> Validators personalizados
   +-> Sanitizacion de input

6. Auditoria
   |
   +-> Cloud Audit Logs
   +-> Django signals
   +-> Sentry tracking
```

### Headers de Seguridad

```python
# config/settings/security.py

# Content Security Policy
CSP_DEFAULT_SRC = ("'self'",)
CSP_SCRIPT_SRC = ("'self'", "htmx.org", "cdn.jsdelivr.net")
CSP_STYLE_SRC = ("'self'", "'unsafe-inline'", "cdn.jsdelivr.net")
CSP_IMG_SRC = ("'self'", "data:", "storage.googleapis.com")

# HTTP Strict Transport Security
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Cookie Security
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
```

---

## Performance

### Optimizaciones Implementadas

1. **Database**
   - Indices en campos frecuentemente consultados
   - `select_related` y `prefetch_related` para evitar N+1
   - Replica de lectura para reportes

2. **Cache**
   - Cache de vistas con `django-redis`
   - Cache de queries frecuentes
   - Cache de sesiones

3. **CDN**
   - Archivos estaticos servidos via Cloud CDN
   - Media files con cache largo

4. **Async**
   - Tareas pesadas en Celery
   - Procesamiento de video asincrono
   - Generacion de reportes en background

### Metricas Objetivo

| Metrica | Objetivo | Actual |
|---------|----------|--------|
| TTFB | < 200ms | - |
| P95 Latencia | < 500ms | - |
| Uptime | 99.5% | - |
| Error Rate | < 0.1% | - |

---

## Referencias

- [Django Architecture Patterns](https://docs.djangoproject.com/)
- [12 Factor App](https://12factor.net/)
- [GCP Architecture Framework](https://cloud.google.com/architecture/framework)
- [Domain-Driven Design](https://martinfowler.com/bliki/DomainDrivenDesign.html)
