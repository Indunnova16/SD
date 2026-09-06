"""Cliente Gemini multimodal (best-effort) para el portal de feedback.

Capacidad usada por el portal de tickets de SD (issue #71 ronda 3 — bounce=2,
FIX_INCOMPLETO x2 por diferir esta pieza sin preguntarle al cliente):

  `transcribir_media(data, mime)` — audio/video/imagen/PDF → texto.

`proponer_titulo_descripcion(adjuntos, texto_libre)` se porta también por
paridad con el resto de apps hermanas del portal de tickets (mismo archivo,
mismo path), aunque el flujo actual de SD (`services.procesar_archivos_subidos`
/ `nuevo_view`) no la invoca todavía — SD no tiene el caso de "asunto o
descripción débiles" que dispara esta función en Piloto.

Ambas funciones son **best-effort**: si `GEMINI_API_KEY` no está configurado
o la llamada falla por cualquier motivo, degradan a un fallback silencioso
(cadena vacía / texto tal cual) — NUNCA bloquean la creación del ticket. Esto
es intencional (calca el comportamiento ya probado en prod de Arcopack/Piloto)
y significa que el portal funciona sin esta pieza; solo se pierde la
transcripción si `GEMINI_API_KEY` no está montado.

**IMPORTANTE (ver F2 de issue #71 ronda 3):** este módulo usa el SDK
`google-genai` con `GEMINI_API_KEY` (API key directa), **NO** Vertex AI /
ADC — a pesar de que el estándar general del portafolio para IA es Vertex
(memoria `indunnova_llm_gemini_vertex`). Los 3 hermanos que implementan esta
MISMA funcionalidad de transcripción de adjuntos del portal de feedback
(Arcopack original, Piloto, FormasFuturo) usan los 3 `genai.Client(api_key=...)`
— nunca `vertexai.init()`. Reusa el secret COMPARTIDO
`arcopack-feedback-gemini-key` (Secret Manager, proyecto `appsindunnova`),
mismo patrón que `GITHUB_FEEDBACK_TOKEN` ya reusa `arcopack-feedback-github-token`
(ver memoria `feedback_portal_cliente_patron_arcopack`, más específica que el
estándar general para este módulo puntual).

Patrón portado literalmente de `Piloto/apps/feedback/gemini_client.py` (a su
vez basado en `feedback/gemini_client.py` de Arcopack).
"""

import json
import logging
import re

from django.conf import settings

logger = logging.getLogger(__name__)


_PROMPT_AUDIO = (
    "Transcribe literalmente este audio en su idioma original (sin traducir).\n"
    "- Si el audio dura más de 60 segundos, agrega al INICIO una línea con un\n"
    "  resumen breve (1-2 líneas máximo), prefijada por `**Resumen:** `.\n"
    "- Si hay silencio o el audio es inaudible, responde solo `[inaudible]`.\n"
    "- NO agregues introducciones tipo 'Aquí está la transcripción'. Solo el\n"
    "  texto resultante.\n"
    "- Conserva las pausas naturales con saltos de línea entre frases largas."
)

_PROMPT_VIDEO = (
    "Analiza este video. Devuelve en este orden:\n"
    "1) Línea iniciada por `**Resumen:**` describiendo en 1 línea qué se ve.\n"
    "2) Línea iniciada por `**Transcripción:**` seguida del texto literal del\n"
    "   audio del video (idioma original, sin traducir).\n"
    "Si el video no tiene audio o es solo visual, describe lo que se ve en\n"
    "2-3 líneas precedidas por `**Visual:**`."
)

_PROMPT_PDF = (
    "Extrae el contenido textual completo de este PDF en su idioma original.\n"
    "- Si tiene más de 5 páginas, antepone una línea `**Resumen:** ...` de\n"
    "  1-2 líneas con la idea central del documento.\n"
    "- Conserva los títulos con `## ` o `### ` según jerarquía visual.\n"
    "- Tablas: convierte a markdown si caben; si son grandes, descríbelas.\n"
    "- Si es un escaneo, haz OCR del texto visible.\n"
    "- NO agregues introducciones. Solo el texto extraído."
)

_PROMPT_IMAGEN = (
    "Analiza esta imagen para anexarla a un issue de soporte/desarrollo del\n"
    "portal de tickets de SD - Cursos (sistema multi-propósito: cursos,\n"
    "inspecciones y pagos).\n"
    "Devuelve en este orden:\n"
    "1) Línea iniciada por `**Descripción:**` con 1-2 líneas que resuman QUÉ\n"
    "   se ve (pantalla del aplicativo, mensaje de error, formulario, captura\n"
    "   de móvil, foto física, etc.) y CUÁL es la situación visible.\n"
    "2) Línea iniciada por `**Texto visible:**` con OCR del texto relevante\n"
    "   (mensajes de error, títulos, labels, valores en formularios). Si no\n"
    "   hay texto legible, omite esta sección.\n"
    "NO agregues introducciones. Idioma original."
)

_PROMPT_TITULO_DESCRIPCION = """Eres un asistente que ayuda a crear issues de soporte/desarrollo para el portal de tickets de SD - Cursos.

A partir del texto y los adjuntos transcritos abajo, propone un título corto y una descripción clara para el issue.

Reglas:
- Título: máximo 90 caracteres, descriptivo y específico, sin emojis.
- Descripción: 2-5 frases que resuman QUÉ pasa, DÓNDE (módulo si se infiere) y CÓMO se reproduce o qué se solicita.
- Idioma: español (Colombia).
- NO inventes datos que no estén en el contexto.
- Si solo hay un audio/imagen sin texto explícito, infiere del contenido transcrito.

Devuelve SOLO JSON válido con esta forma exacta:
{"titulo": "...", "descripcion": "..."}

CONTEXTO:
"""


def _mime_base(mime: str) -> str:
    if not mime:
        return ""
    return mime.split(";", 1)[0].strip().lower()


def _get_genai_client():
    """Devuelve un cliente google.genai usando GEMINI_API_KEY."""
    from google import genai  # lazy

    api_key = (getattr(settings, "GEMINI_API_KEY", "") or "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY no configurado")
    return genai.Client(api_key=api_key)


def transcribir_media(data: bytes, mime: str) -> str:
    """Transcribe audio/video/imagen/PDF con Gemini. Retorna texto o ''.

    Nunca propaga excepciones — si falla (o no hay API key), retorna cadena
    vacía y loggea.
    """
    if not getattr(settings, "GEMINI_TRANSCRIBE_ENABLED", True):
        return ""
    if not data:
        return ""

    size = len(data)
    max_bytes = getattr(settings, "GEMINI_TRANSCRIBE_MAX_BYTES", 20 * 1024 * 1024)
    if size > max_bytes:
        logger.warning("Media de %d bytes excede límite %d para transcripción", size, max_bytes)
        return ""

    base = _mime_base(mime)
    if base.startswith("audio/"):
        prompt, kind = _PROMPT_AUDIO, "audio"
    elif base.startswith("video/"):
        prompt, kind = _PROMPT_VIDEO, "video"
    elif base == "application/pdf":
        prompt, kind = _PROMPT_PDF, "pdf"
    elif base.startswith("image/"):
        prompt, kind = _PROMPT_IMAGEN, "imagen"
    else:
        return ""

    try:
        from google.genai import types

        client = _get_genai_client()
        model = getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash")
        response = client.models.generate_content(
            model=model,
            contents=[
                types.Part.from_bytes(data=data, mime_type=base),
                prompt,
            ],
            config=types.GenerateContentConfig(temperature=0.1),
        )
        text = (getattr(response, "text", None) or "").strip()
        logger.info("Transcripción %s OK: %d chars", kind, len(text))
        return text
    except Exception as exc:
        logger.error("Transcripción Gemini falló (%s): %s", kind, exc, exc_info=True)
        return ""


def _parse_gemini_json(raw: str) -> dict | None:
    """Parsea JSON aunque venga envuelto en code fences ```json ... ```."""
    if not raw:
        return None
    s = raw.strip()
    # Quitar fences si los hay
    s = re.sub(r"^```(?:json)?\s*\n?", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\n?\s*```\s*$", "", s)
    try:
        data = json.loads(s)
        if isinstance(data, dict):
            return data
    except ValueError:
        pass
    return None


def proponer_titulo_descripcion(adjuntos_resumen: list, texto_libre: str) -> dict:
    """Propone título y descripción usando Gemini.

    Args:
        adjuntos_resumen: lista de dicts {nombre, tipo, transcripcion}
        texto_libre: lo que el usuario escribió (puede estar vacío)

    Returns:
        {"titulo": "...", "descripcion": "..."} — si Gemini falla (o no hay
        API key) retorna defaults razonables a partir del primer adjunto/texto.
    """
    contexto = ""
    if texto_libre:
        contexto += f"TEXTO DEL USUARIO:\n{texto_libre.strip()}\n\n"
    for i, a in enumerate(adjuntos_resumen, start=1):
        tr = (a.get("transcripcion") or "").strip()
        if tr:
            contexto += f"ADJUNTO {i} ({a.get('tipo', '?')} — {a.get('nombre', '?')}):\n{tr}\n\n"
        else:
            contexto += f"ADJUNTO {i} ({a.get('tipo', '?')} — {a.get('nombre', '?')}): [sin transcripción]\n\n"

    fallback_titulo = (texto_libre or "Reporte desde portal").strip().split("\n", 1)[0][:90]
    fallback_descripcion = (texto_libre or "Reporte enviado desde el portal con adjuntos.").strip()[
        :500
    ]
    fallback = {"titulo": fallback_titulo, "descripcion": fallback_descripcion}

    if not contexto.strip():
        return fallback

    try:
        from google.genai import types

        client = _get_genai_client()
        model = getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash")
        response = client.models.generate_content(
            model=model,
            contents=[_PROMPT_TITULO_DESCRIPCION + contexto],
            config=types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",
            ),
        )
        raw = (getattr(response, "text", None) or "").strip()
        data = _parse_gemini_json(raw)
        if data:
            titulo = (data.get("titulo") or "").strip().strip('"').strip("'")[:90]
            descripcion = (data.get("descripcion") or "").strip().strip('"').strip("'")[:500]
            if titulo and descripcion:
                return {"titulo": titulo, "descripcion": descripcion}
    except Exception as exc:
        logger.error("Sugerencia título/descripción falló: %s", exc, exc_info=True)

    return fallback
