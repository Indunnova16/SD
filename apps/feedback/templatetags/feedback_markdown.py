"""
Filtro `markdownify` para renderizar cuerpos de comentarios de GitHub en el
portal público de tickets (issue #71 ronda 2).

Por qué existe: el cliente reclamó que "el usuario no puede ver los
comentarios ni imágenes en el ticket", y el requisito literal del issue es
*"que el usuario pueda ver las imágenes cargadas en GH desde su portal"*.
Los comentarios de GitHub llegan como markdown, y las imágenes vienen
embebidas de dos formas distintas:

    ![captura](https://github.com/user-attachments/assets/<uuid>)
    <img width="1236" alt="Image" src="https://github.com/user-attachments/assets/<uuid>">

La segunda es HTML crudo — es literalmente el formato que usó el revisor en
el comentario que originó este trabajo. Por eso NO alcanza con escapar todo
ni con un `linebreaks`: hay que renderizar markdown Y dejar pasar `<img>`.

Dejar pasar HTML de GitHub es dejar pasar HTML escrito por terceros hacia
una página pública y anónima, así que la salida se sanea SIEMPRE con bleach
(allowlist de tags/atributos/protocolos). Sin ese paso, cualquiera que
comente `<script>` en el issue público ejecuta JS en el portal.
"""

from django import template
from django.utils.safestring import mark_safe

import bleach
import markdown as markdown_lib

register = template.Library()

# Allowlist deliberadamente chica: lo que aparece en un comentario de
# soporte. `img` es el que resuelve el requisito del cliente.
TAGS_PERMITIDOS = [
    "p",
    "br",
    "hr",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "strong",
    "em",
    "b",
    "i",
    "u",
    "del",
    "s",
    "ul",
    "ol",
    "li",
    "blockquote",
    "pre",
    "code",
    "a",
    "img",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
]

ATRIBUTOS_PERMITIDOS = {
    "a": ["href", "title", "rel", "target"],
    "img": ["src", "alt", "title", "width", "height"],
    "th": ["align"],
    "td": ["align"],
}

# Sin `data:` — una imagen `data:` en un comentario de terceros no aporta
# nada al caso de uso y amplía la superficie.
PROTOCOLOS_PERMITIDOS = ["http", "https", "mailto"]


@register.filter(name="markdownify")
def markdownify(value):
    """Renderiza markdown a HTML saneado, listo para `{{ ... }}` en template.

    Devuelve cadena vacía si `value` es vacío/None.
    """
    if not value:
        return ""

    html = markdown_lib.markdown(
        str(value),
        extensions=["fenced_code", "tables", "nl2br", "sane_lists"],
        output_format="html",
    )

    limpio = bleach.clean(
        html,
        tags=TAGS_PERMITIDOS,
        attributes=ATRIBUTOS_PERMITIDOS,
        protocols=PROTOCOLOS_PERMITIDOS,
        strip=True,
    )

    # `mark_safe` es seguro acá porque `limpio` ya pasó por bleach: es la
    # salida de la allowlist, no input de usuario sin filtrar.
    return mark_safe(limpio)  # noqa: S308
