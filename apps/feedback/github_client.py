"""
Cliente GitHub REST minimal para el portal de tickets de feedback (apps.feedback).

Encapsula las únicas operaciones que necesita el portal contra la API de
GitHub: crear un issue por cada ticket reportado, asegurar que la label
'portal-web' exista en el repo destino, listar los comentarios de un issue
(para mostrarlos en el detalle del ticket) y cerrar un issue cuando el
usuario resuelve su caso. NO es un cliente genérico — deja fuera todo lo
que el portal no usa (paginación real, otras rutas, etc).

Toda excepción de red o de status inesperado se normaliza a
GitHubClientError para que el caller (apps.feedback.services) capture un
único tipo de excepción, sin acoplarse a requests.exceptions.*.
"""

import requests
from django.conf import settings

GITHUB_API_BASE = "https://api.github.com"
TITLE_MAX_LENGTH = 256
LABEL_PORTAL_WEB = "portal-web"
LABEL_PORTAL_WEB_COLOR = "fbca04"
LABEL_PORTAL_WEB_DESCRIPTION = "Ticket reportado desde el portal web de feedback"
DEFAULT_TIMEOUT_SECONDS = 15

# Timeout más corto para leer comentarios: corre en el camino crítico de
# renderizar el detalle del ticket, así que no puede colgar la página 15 s
# cuando GitHub está lento.
READ_TIMEOUT_SECONDS = 8
COMENTARIOS_POR_PAGINA = 100

TIPO_IMAGEN = "imagen"
ICONO_POR_TIPO = {"audio": "🔊", "video": "🎬"}


class GitHubClientError(Exception):
    """Cualquier fallo al hablar con la API de GitHub (config, red, status)."""


class GitHubFeedbackClient:
    """Cliente REST minimal contra la API de GitHub para el portal de tickets."""

    def __init__(self, token=None, repo=None):
        self.token = (token if token is not None else settings.GITHUB_FEEDBACK_TOKEN).strip()
        self.repo = (repo if repo is not None else settings.GITHUB_FEEDBACK_REPO).strip()

        if not self.token:
            raise GitHubClientError(
                "GITHUB_FEEDBACK_TOKEN no configurado (vacío tras strip). "
                "Verificá el secret en Secret Manager / variable de entorno."
            )
        if not self.repo:
            raise GitHubClientError(
                "GITHUB_FEEDBACK_REPO no configurado (vacío tras strip). "
                "Debe ser 'owner/repo', ej. 'Indunnova16/SD'."
            )

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    @staticmethod
    def _bloque_transcripcion(transcripcion):
        """Renderiza la transcripción IA de un adjunto como blockquote markdown.

        Issue #71 ronda 3: portado de `Piloto/apps/feedback/github_client.py`
        (`_bloque_transcripcion`), formato exacto que el cliente ya vio y
        adjuntó como referencia. Devuelve `""` si no hay transcripción (el
        caller simplemente omite el bloque para ese adjunto — ningún fallo
        de Gemini debe dejar un encabezado vacío en el issue).
        """
        if not transcripcion or not transcripcion.strip():
            return ""
        lineas = transcripcion.strip().splitlines()
        bq = "\n".join(f"> {l}" if l.strip() else ">" for l in lineas)
        return f"**Transcripción:**\n{bq}"

    def _build_body(self, descripcion, nombre_reportante, adjuntos=None):
        lineas = [
            descripcion,
            "",
            "---",
            f"**Reportado por:** {nombre_reportante}",
        ]
        if adjuntos:
            lineas.append("")
            lineas.append("**Adjuntos:**")
            for adjunto in adjuntos:
                if isinstance(adjunto, dict):
                    nombre = adjunto.get("nombre")
                    url = adjunto.get("url")
                    tipo = adjunto.get("tipo") or TIPO_IMAGEN
                    transcripcion = adjunto.get("transcripcion") or ""
                else:
                    nombre, url, tipo = None, adjunto, TIPO_IMAGEN
                    transcripcion = ""
                nombre = nombre or "adjunto"
                # Solo las imágenes van como `![]()`. Un audio/video
                # embebido así se renderiza como imagen rota en GitHub, así
                # que van como link con el ícono del tipo.
                if tipo == TIPO_IMAGEN:
                    lineas.append(f"![{nombre}]({url})")
                else:
                    lineas.append(f"{ICONO_POR_TIPO.get(tipo, '📎')} [{nombre}]({url})")
                # Issue #71 ronda 3 — el ÚNICO reclamo vigente del cliente
                # (pedido 2 veces, diferido 2 veces sin preguntar): que la
                # transcripción/descripción generada por IA llegue al issue
                # de GitHub, no solo a la base de datos.
                bloque_tr = self._bloque_transcripcion(transcripcion)
                if bloque_tr:
                    lineas.append(bloque_tr)
        return "\n".join(lineas)

    def crear_issue(self, ticket_id, asunto, descripcion, nombre_reportante, adjuntos=None):
        """Crea un issue en GitHub para el ticket dado.

        Devuelve {"number": int, "html_url": str, "id": int}.
        Levanta GitHubClientError ante cualquier fallo (red, status != 201).
        """
        title = f"[Portal] {asunto}"[:TITLE_MAX_LENGTH]
        body = self._build_body(descripcion, nombre_reportante, adjuntos=adjuntos)
        payload = {
            "title": title,
            "body": body,
            "labels": [LABEL_PORTAL_WEB],
            "assignees": ["Indunnova"],
        }

        try:
            response = requests.post(
                f"{GITHUB_API_BASE}/repos/{self.repo}/issues",
                json=payload,
                headers=self._headers(),
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise GitHubClientError(
                f"Error de red creando issue en GitHub para ticket {ticket_id}: {exc}"
            ) from exc

        if response.status_code != 201:
            raise GitHubClientError(
                f"GitHub devolvió status inesperado creando issue para ticket "
                f"{ticket_id}: {response.status_code} — {response.text}"
            )

        data = response.json()
        return {
            "number": data["number"],
            "html_url": data["html_url"],
            "id": data["id"],
        }

    def listar_comentarios(self, issue_number):
        """Lista los comentarios de un issue, del más viejo al más nuevo.

        Devuelve una lista de dicts `{autor, avatar, cuerpo, created_at,
        url}` — solo los campos que el portal renderiza, no el payload
        crudo de GitHub (que es enorme y trae datos que no queremos filtrar
        a una superficie pública/anónima).

        Levanta GitHubClientError ante cualquier fallo (red, status != 200).
        """
        try:
            response = requests.get(
                f"{GITHUB_API_BASE}/repos/{self.repo}/issues/{issue_number}/comments",
                params={"per_page": COMENTARIOS_POR_PAGINA},
                headers=self._headers(),
                timeout=READ_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise GitHubClientError(
                f"Error de red listando comentarios del issue {issue_number}: {exc}"
            ) from exc

        if response.status_code != 200:
            raise GitHubClientError(
                f"GitHub devolvió status inesperado listando comentarios del "
                f"issue {issue_number}: {response.status_code} — {response.text}"
            )

        comentarios = []
        for item in response.json():
            usuario = item.get("user") or {}
            comentarios.append(
                {
                    "autor": usuario.get("login") or "equipo",
                    "avatar": usuario.get("avatar_url") or "",
                    "cuerpo": item.get("body") or "",
                    "created_at": item.get("created_at") or "",
                    "url": item.get("html_url") or "",
                }
            )
        return comentarios

    def comentar_issue(self, issue_number, cuerpo):
        """Publica un comentario en un issue SIN cerrarlo.

        Issue #71 ronda 4: extraído del bloque que `cerrar_issue` ya usaba
        para postear el comentario de "quién resolvió" — reutilizado acá
        para que el portal pueda comentar un ticket (seguimiento) de forma
        independiente de resolverlo.

        Devuelve el `id` del comentario creado. Levanta GitHubClientError
        ante cualquier fallo (red, status != 201).
        """
        try:
            response = requests.post(
                f"{GITHUB_API_BASE}/repos/{self.repo}/issues/{issue_number}/comments",
                json={"body": cuerpo},
                headers=self._headers(),
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise GitHubClientError(
                f"Error de red comentando el issue {issue_number}: {exc}"
            ) from exc

        if response.status_code != 201:
            raise GitHubClientError(
                f"GitHub devolvió status inesperado comentando el issue "
                f"{issue_number}: {response.status_code} — {response.text}"
            )
        return response.json().get("id")

    def cerrar_issue(self, issue_number, comentario=None):
        """Cierra un issue; si viene `comentario`, lo postea antes de cerrar.

        El comentario va primero a propósito: deja registro de QUIÉN resolvió
        desde el portal antes de que el issue quede cerrado.

        Devuelve {"state": "closed", "comment_id": int|None}.
        Levanta GitHubClientError ante cualquier fallo.
        """
        comment_id = None

        if comentario:
            comment_id = self.comentar_issue(issue_number, comentario)

        try:
            response = requests.patch(
                f"{GITHUB_API_BASE}/repos/{self.repo}/issues/{issue_number}",
                json={"state": "closed"},
                headers=self._headers(),
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise GitHubClientError(
                f"Error de red cerrando el issue {issue_number}: {exc}"
            ) from exc

        if response.status_code != 200:
            raise GitHubClientError(
                f"GitHub devolvió status inesperado cerrando el issue "
                f"{issue_number}: {response.status_code} — {response.text}"
            )

        return {"state": "closed", "comment_id": comment_id}

    def asegurar_label_portal_web(self):
        """Crea la label 'portal-web' en el repo si no existe.

        Idempotente: 201 (creada) y 422 (ya existe) se tratan como éxito
        silencioso. Cualquier otro status levanta GitHubClientError.
        """
        payload = {
            "name": LABEL_PORTAL_WEB,
            "color": LABEL_PORTAL_WEB_COLOR,
            "description": LABEL_PORTAL_WEB_DESCRIPTION,
        }

        try:
            response = requests.post(
                f"{GITHUB_API_BASE}/repos/{self.repo}/labels",
                json=payload,
                headers=self._headers(),
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise GitHubClientError(
                f"Error de red asegurando label '{LABEL_PORTAL_WEB}' en GitHub: {exc}"
            ) from exc

        if response.status_code in (201, 422):
            return

        raise GitHubClientError(
            f"GitHub devolvió status inesperado creando label '{LABEL_PORTAL_WEB}': "
            f"{response.status_code} — {response.text}"
        )
