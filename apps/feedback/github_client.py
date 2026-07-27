"""
Cliente GitHub REST minimal para el portal de tickets de feedback (apps.feedback).

Encapsula las dos únicas operaciones que necesita el portal contra la API
de GitHub: crear un issue por cada ticket reportado y asegurar que la label
'portal-web' exista en el repo destino. NO es un cliente genérico — deja
fuera todo lo que el portal no usa (paginación, otras rutas, etc).

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
                nombre = adjunto.get("nombre") if isinstance(adjunto, dict) else None
                url = adjunto.get("url") if isinstance(adjunto, dict) else adjunto
                nombre = nombre or "adjunto"
                lineas.append(f"![{nombre}]({url})")
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
