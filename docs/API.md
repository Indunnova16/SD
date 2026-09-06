# Documentacion de API - SD LMS

Guia de referencia para la API REST del Sistema LMS de S.D. S.A.S.

## Tabla de Contenidos

- [Informacion General](#informacion-general)
- [Autenticacion](#autenticacion)
- [Endpoints Principales](#endpoints-principales)
- [Ejemplos de Uso](#ejemplos-de-uso)
- [Rate Limiting](#rate-limiting)
- [Errores](#errores)

---

## Informacion General

### Base URL

| Ambiente | URL |
|----------|-----|
| Produccion | `https://api.lms.sd.com.co/api/v1` |
| Staging | `https://api-staging.lms.sd.com.co/api/v1` |
| Desarrollo | `http://localhost:8000/api/v1` |

### Formato de Respuesta

Todas las respuestas usan formato JSON con la siguiente estructura:

```json
{
  "data": { ... },
  "meta": {
    "timestamp": "2024-01-15T10:30:00Z",
    "request_id": "abc123"
  }
}
```

Para listas paginadas:

```json
{
  "count": 100,
  "next": "https://api.lms.sd.com.co/api/v1/courses/?page=2",
  "previous": null,
  "results": [ ... ]
}
```

### Headers Comunes

| Header | Requerido | Descripcion |
|--------|-----------|-------------|
| `Authorization` | Si | Token JWT: `Bearer <access_token>` |
| `Content-Type` | Si | `application/json` |
| `Accept` | No | `application/json` |
| `Accept-Language` | No | `es` (default), `en` |
| `X-Request-ID` | No | ID unico para trazabilidad |

---

## Autenticacion

La API usa autenticacion basada en JWT (JSON Web Tokens) siguiendo el estandar RFC 7519.

### Flujo de Autenticacion

```
+--------+                               +--------+
|        | 1. POST /auth/token/          |        |
| Cliente|  (email + password)           | Server |
|        |------------------------------>|        |
|        |                               |        |
|        | 2. {access_token,             |        |
|        |     refresh_token}            |        |
|        |<------------------------------|        |
|        |                               |        |
|        | 3. GET /courses/              |        |
|        |  Authorization: Bearer xxx    |        |
|        |------------------------------>|        |
|        |                               |        |
|        | 4. {data: [...]}              |        |
|        |<------------------------------|        |
+--------+                               +--------+
```

### Obtener Token

**POST** `/api/v1/auth/token/`

Obtiene un par de tokens (access y refresh) usando credenciales.

**Request:**

```json
{
  "email": "usuario@sd-sas.com",
  "password": "contraseña_segura"
}
```

**Response (200 OK):**

```json
{
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Tiempos de Expiracion:**
- Access Token: 15 minutos
- Refresh Token: 7 dias

### Refrescar Token

**POST** `/api/v1/auth/token/refresh/`

Obtiene un nuevo access token usando el refresh token.

**Request:**

```json
{
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response (200 OK):**

```json
{
  "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

### Verificar Token

**POST** `/api/v1/auth/token/verify/`

Verifica si un token es valido.

**Request:**

```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response (200 OK):**

```json
{}
```

### Cerrar Sesion (Blacklist Token)

**POST** `/api/v1/auth/token/logout/`

Invalida el refresh token actual.

**Request:**

```json
{
  "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response (200 OK):**

```json
{
  "detail": "Sesion cerrada exitosamente"
}
```

---

## Endpoints Principales

### Usuarios

#### Obtener Usuario Actual

**GET** `/api/v1/auth/me/`

Retorna la informacion del usuario autenticado.

**Response:**

```json
{
  "id": 1,
  "email": "usuario@sd-sas.com",
  "first_name": "Juan",
  "last_name": "Perez",
  "full_name": "Juan Perez",
  "document_type": "CC",
  "document_number": "12345678",
  "phone": "+57 300 123 4567",
  "job_position": "Liniero",
  "job_profile": "LINIERO",
  "status": "active",
  "is_active": true,
  "created_at": "2024-01-01T00:00:00Z"
}
```

#### Cambiar Contrasena

**POST** `/api/v1/auth/password/change/`

**Request:**

```json
{
  "old_password": "contrasena_actual",
  "new_password": "nueva_contrasena_segura"
}
```

**Response (200 OK):**

```json
{
  "detail": "Contrasena actualizada exitosamente"
}
```

#### Listar Usuarios (Admin)

**GET** `/api/v1/auth/users/`

**Query Parameters:**

| Parametro | Tipo | Descripcion |
|-----------|------|-------------|
| `page` | int | Numero de pagina (default: 1) |
| `page_size` | int | Items por pagina (max: 100) |
| `search` | string | Busqueda por nombre o email |
| `status` | string | Filtrar por estado |
| `job_profile` | string | Filtrar por perfil |

---

### Cursos

#### Listar Cursos

**GET** `/api/v1/courses/courses/`

**Query Parameters:**

| Parametro | Tipo | Descripcion |
|-----------|------|-------------|
| `category` | int | ID de categoria |
| `status` | string | `draft`, `published`, `archived` |
| `is_mandatory` | bool | Cursos obligatorios |
| `search` | string | Busqueda por titulo |
| `ordering` | string | Campo de ordenamiento |

**Response:**

```json
{
  "count": 25,
  "next": "https://api.lms.sd.com.co/api/v1/courses/courses/?page=2",
  "previous": null,
  "results": [
    {
      "id": 1,
      "title": "Seguridad en Trabajos en Altura",
      "slug": "seguridad-trabajos-altura",
      "description": "Curso fundamental de seguridad...",
      "category": {
        "id": 1,
        "name": "Seguridad Industrial"
      },
      "duration_hours": 8,
      "validity_months": 12,
      "is_mandatory": true,
      "status": "published",
      "thumbnail": "https://storage.../thumbnail.jpg",
      "modules_count": 5,
      "lessons_count": 20,
      "created_at": "2024-01-01T00:00:00Z"
    }
  ]
}
```

#### Obtener Curso

**GET** `/api/v1/courses/courses/{id}/`

**Response:**

```json
{
  "id": 1,
  "title": "Seguridad en Trabajos en Altura",
  "slug": "seguridad-trabajos-altura",
  "description": "Curso fundamental de seguridad...",
  "objectives": [
    "Identificar riesgos en trabajos en altura",
    "Aplicar medidas de prevencion"
  ],
  "category": { ... },
  "duration_hours": 8,
  "validity_months": 12,
  "is_mandatory": true,
  "prerequisites": [
    {
      "id": 2,
      "title": "Induccion General"
    }
  ],
  "modules": [
    {
      "id": 1,
      "title": "Introduccion",
      "order": 1,
      "lessons_count": 4
    }
  ],
  "instructors": [ ... ],
  "created_at": "2024-01-01T00:00:00Z"
}
```

#### Inscribirse en Curso

**POST** `/api/v1/courses/courses/{id}/enroll/`

**Response (201 Created):**

```json
{
  "id": 100,
  "user": 1,
  "course": 1,
  "status": "enrolled",
  "progress": 0,
  "enrolled_at": "2024-01-15T10:30:00Z",
  "expires_at": null
}
```

#### Mis Inscripciones

**GET** `/api/v1/courses/my-enrollments/`

**Query Parameters:**

| Parametro | Tipo | Descripcion |
|-----------|------|-------------|
| `status` | string | `enrolled`, `in_progress`, `completed` |

**Response:**

```json
{
  "results": [
    {
      "id": 100,
      "course": {
        "id": 1,
        "title": "Seguridad en Trabajos en Altura",
        "thumbnail": "https://..."
      },
      "status": "in_progress",
      "progress": 45.5,
      "enrolled_at": "2024-01-15T10:30:00Z",
      "last_accessed_at": "2024-01-20T14:00:00Z"
    }
  ]
}
```

#### Actualizar Progreso de Leccion

**POST** `/api/v1/courses/enrollments/{enrollment_id}/lessons/{lesson_id}/progress/`

**Request:**

```json
{
  "time_spent_seconds": 300,
  "completed": true
}
```

**Response:**

```json
{
  "lesson_id": 5,
  "completed": true,
  "completed_at": "2024-01-20T14:05:00Z",
  "enrollment_progress": 50.0
}
```

---

### Evaluaciones

#### Listar Evaluaciones de un Curso

**GET** `/api/v1/assessments/assessments/?course={course_id}`

**Response:**

```json
{
  "results": [
    {
      "id": 1,
      "title": "Evaluacion Final - Trabajo en Altura",
      "type": "final",
      "passing_score": 80,
      "max_attempts": 3,
      "time_limit_minutes": 60,
      "questions_count": 20,
      "is_randomized": true
    }
  ]
}
```

#### Iniciar Intento de Evaluacion

**POST** `/api/v1/assessments/assessments/{id}/start/`

**Response:**

```json
{
  "attempt_id": 50,
  "started_at": "2024-01-20T15:00:00Z",
  "expires_at": "2024-01-20T16:00:00Z",
  "questions": [
    {
      "id": 1,
      "order": 1,
      "text": "Cual es la altura minima para requerir proteccion contra caidas?",
      "type": "single_choice",
      "options": [
        {"id": 1, "text": "1.5 metros"},
        {"id": 2, "text": "1.8 metros"},
        {"id": 3, "text": "2.0 metros"}
      ]
    }
  ]
}
```

#### Enviar Respuestas

**POST** `/api/v1/assessments/attempts/{id}/submit/`

**Request:**

```json
{
  "answers": [
    {"question_id": 1, "selected_options": [2]},
    {"question_id": 2, "selected_options": [1, 3]},
    {"question_id": 3, "text_answer": "Respuesta abierta..."}
  ]
}
```

**Response:**

```json
{
  "attempt_id": 50,
  "score": 85.0,
  "passed": true,
  "completed_at": "2024-01-20T15:45:00Z",
  "time_spent_minutes": 45,
  "correct_answers": 17,
  "total_questions": 20,
  "feedback": "Excelente trabajo! Has aprobado la evaluacion."
}
```

---

### Certificados

#### Listar Mis Certificados

**GET** `/api/v1/certifications/certificates/`

**Response:**

```json
{
  "results": [
    {
      "id": 1,
      "certificate_number": "SD-202401-A1B2C3D4",
      "course": {
        "id": 1,
        "title": "Seguridad en Trabajos en Altura"
      },
      "status": "issued",
      "score": 85.0,
      "issued_at": "2024-01-20T16:00:00Z",
      "expires_at": "2025-01-20T16:00:00Z",
      "certificate_url": "https://storage.../cert_SD-202401-A1B2C3D4.pdf",
      "verification_url": "https://lms.sd.com.co/certificates/verify/SD-202401-A1B2C3D4/"
    }
  ]
}
```

#### Verificar Certificado (Publico)

**GET** `/api/v1/certifications/verify/{certificate_number}/`

**Response (Certificado Valido):**

```json
{
  "valid": true,
  "certificate": {
    "number": "SD-202401-A1B2C3D4",
    "user_name": "Juan Perez",
    "course_title": "Seguridad en Trabajos en Altura",
    "issued_at": "2024-01-20T16:00:00Z",
    "expires_at": "2025-01-20T16:00:00Z",
    "score": 85.0
  }
}
```

**Response (Certificado Invalido):**

```json
{
  "valid": false,
  "reason": "Este certificado ha expirado",
  "expired_at": "2024-01-20T16:00:00Z"
}
```

---

### Rutas de Aprendizaje

#### Listar Rutas de Aprendizaje

**GET** `/api/v1/learning-paths/paths/`

**Response:**

```json
{
  "results": [
    {
      "id": 1,
      "title": "Formacion Completa Liniero",
      "description": "Ruta de formacion integral...",
      "courses_count": 5,
      "total_hours": 40,
      "is_mandatory": true,
      "courses": [
        {
          "id": 1,
          "title": "Induccion General",
          "order": 1,
          "is_prerequisite": false
        },
        {
          "id": 2,
          "title": "Seguridad en Trabajos en Altura",
          "order": 2,
          "is_prerequisite": true
        }
      ]
    }
  ]
}
```

#### Mis Rutas de Aprendizaje

**GET** `/api/v1/learning-paths/my-paths/`

**Response:**

```json
{
  "results": [
    {
      "path": { ... },
      "status": "in_progress",
      "progress": 40.0,
      "courses_completed": 2,
      "courses_total": 5,
      "assigned_at": "2024-01-01T00:00:00Z",
      "current_course": {
        "id": 3,
        "title": "Primeros Auxilios"
      }
    }
  ]
}
```

---

## Ejemplos de Uso

### Python (requests)

```python
import requests

BASE_URL = "https://api.lms.sd.com.co/api/v1"

# Autenticacion
response = requests.post(
    f"{BASE_URL}/auth/token/", json={"email": "usuario@sd-sas.com", "password": "contrasena"}
)
tokens = response.json()
access_token = tokens["access"]

# Headers para requests autenticados
headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

# Obtener cursos
response = requests.get(
    f"{BASE_URL}/courses/courses/", headers=headers, params={"status": "published"}
)
courses = response.json()

# Inscribirse en curso
response = requests.post(f"{BASE_URL}/courses/courses/1/enroll/", headers=headers)
enrollment = response.json()
```

### JavaScript (fetch)

```javascript
const BASE_URL = "https://api.lms.sd.com.co/api/v1";

// Autenticacion
async function login(email, password) {
  const response = await fetch(`${BASE_URL}/auth/token/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password })
  });
  return response.json();
}

// Obtener cursos
async function getCourses(accessToken) {
  const response = await fetch(`${BASE_URL}/courses/courses/`, {
    headers: {
      "Authorization": `Bearer ${accessToken}`,
      "Content-Type": "application/json"
    }
  });
  return response.json();
}

// Uso
const tokens = await login("usuario@sd-sas.com", "contrasena");
const courses = await getCourses(tokens.access);
```

### cURL

```bash
# Obtener token
curl -X POST https://api.lms.sd.com.co/api/v1/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"email": "usuario@sd-sas.com", "password": "contrasena"}'

# Listar cursos
curl -X GET "https://api.lms.sd.com.co/api/v1/courses/courses/?status=published" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." \
  -H "Content-Type: application/json"

# Inscribirse en curso
curl -X POST https://api.lms.sd.com.co/api/v1/courses/courses/1/enroll/ \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIs..." \
  -H "Content-Type: application/json"
```

---

## Rate Limiting

La API implementa rate limiting para proteger contra abusos.

### Limites por Defecto

| Tipo de Usuario | Limite |
|-----------------|--------|
| No autenticado | 30 requests/minuto |
| Autenticado | 100 requests/minuto |
| API Key (integraciones) | 1000 requests/minuto |

### Headers de Rate Limit

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1705320000
```

### Respuesta cuando se excede el limite

**Response (429 Too Many Requests):**

```json
{
  "detail": "Request was throttled. Expected available in 45 seconds.",
  "retry_after": 45
}
```

---

## Errores

### Formato de Error

```json
{
  "detail": "Mensaje de error legible",
  "code": "error_code",
  "errors": {
    "field_name": ["Lista de errores del campo"]
  }
}
```

### Codigos de Estado HTTP

| Codigo | Significado | Descripcion |
|--------|-------------|-------------|
| 200 | OK | Request exitoso |
| 201 | Created | Recurso creado exitosamente |
| 204 | No Content | Request exitoso sin contenido |
| 400 | Bad Request | Request invalido (validacion) |
| 401 | Unauthorized | No autenticado |
| 403 | Forbidden | Sin permisos |
| 404 | Not Found | Recurso no encontrado |
| 405 | Method Not Allowed | Metodo HTTP no soportado |
| 409 | Conflict | Conflicto (ej: duplicado) |
| 422 | Unprocessable Entity | Entidad no procesable |
| 429 | Too Many Requests | Rate limit excedido |
| 500 | Internal Server Error | Error del servidor |

### Errores Comunes

#### Error de Validacion (400)

```json
{
  "detail": "Error de validacion",
  "errors": {
    "email": ["Este campo es requerido"],
    "password": ["La contrasena debe tener al menos 8 caracteres"]
  }
}
```

#### Token Expirado (401)

```json
{
  "detail": "Token expirado",
  "code": "token_not_valid"
}
```

#### Sin Permisos (403)

```json
{
  "detail": "No tiene permisos para realizar esta accion"
}
```

#### Recurso No Encontrado (404)

```json
{
  "detail": "No encontrado"
}
```

#### Conflicto de Negocio (409)

```json
{
  "detail": "Ya esta inscrito en este curso",
  "code": "already_enrolled"
}
```

---

## Paginacion

La API usa paginacion basada en paginas para listas largas.

### Parametros de Paginacion

| Parametro | Tipo | Default | Max | Descripcion |
|-----------|------|---------|-----|-------------|
| `page` | int | 1 | - | Numero de pagina |
| `page_size` | int | 20 | 100 | Items por pagina |

### Respuesta Paginada

```json
{
  "count": 150,
  "next": "https://api.lms.sd.com.co/api/v1/courses/courses/?page=2",
  "previous": null,
  "results": [ ... ]
}
```

---

## Versionado

La API usa versionado en la URL: `/api/v1/`

### Politica de Deprecacion

- Las versiones obsoletas se anuncian con 6 meses de anticipacion
- Se incluye el header `Deprecation` en respuestas de versiones obsoletas:

```
Deprecation: true
Sunset: Sat, 01 Jul 2025 00:00:00 GMT
Link: </api/v2/>; rel="successor-version"
```

---

## Soporte

- **Documentacion interactiva**: `/api/docs/` (Swagger UI)
- **OpenAPI Schema**: `/api/schema/`
- **Email**: api-support@sd-sas.com
