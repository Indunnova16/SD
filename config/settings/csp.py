"""
Content Security Policy compartida por los settings que corren desplegados.

Contexto (SD#76)
----------------
Hasta este cambio la CSP vivía SOLO en ``config/settings/production.py`` y
estaba escrita con las variables planas ``CSP_DEFAULT_SRC`` / ``CSP_SCRIPT_SRC``
/ etc. Eso no emitía ningún header en producción por DOS razones encadenadas:

1. Producción NO corre ``config.settings.production``. El workflow
   ``.github/workflows/deploy.yml`` despliega Cloud Run con
   ``DJANGO_SETTINGS_MODULE=config.settings.cloudrun`` (y los jobs de migrate /
   ensure_admin / axes_reset usan el mismo módulo). ``cloudrun.py`` nunca
   definió nada de CSP.
2. Aunque se hubiera cargado, la versión instalada de django-csp es la **4.0**
   (``requirements/base.txt`` pide ``django-csp>=3.8``, sin pin). Desde 4.0 el
   middleware construye la política leyendo ``CONTENT_SECURITY_POLICY`` /
   ``CONTENT_SECURITY_POLICY_REPORT_ONLY`` (un dict con clave ``DIRECTIVES``).
   Las ``CSP_*`` planas quedaron en ``csp.checks.OUTDATED_SETTINGS``: NO
   alimentan la política, solo disparan el check ``csp.E001``. El resultado es
   un fallo silencioso — middleware activo, cero header.
3. Y ese aviso ``csp.E001`` tampoco se veía, porque ``"csp"`` no estaba en
   ``INSTALLED_APPS`` y los checks se registran desde ``csp/apps.py``. Tres
   capas de silencio encima del mismo bug. Ya se instaló la app (``base.py``),
   así que hoy una ``CSP_*`` plana rompe ``manage.py check`` en vez de pasar
   desapercibida.

Por qué arranca en REPORT-ONLY
------------------------------
La política se emite por defecto como ``Content-Security-Policy-Report-Only``
(ver ``CSP_ENFORCE`` en ``cloudrun.py`` / ``production.py``). El header viaja y
el navegador reporta violaciones en consola, pero NO bloquea nada. Es
deliberado: la app tiene deuda real que una CSP bloqueante rompería de formas
difíciles de diagnosticar (pantallas en blanco, sin error de servidor):

* 29 bloques ``<script>`` inline en templates y solo 10 llevan
  ``nonce="{{ request.csp_nonce }}"``. Entre los que NO lo llevan está el
  portal público de tickets (``apps/feedback/templates/feedback/base.html``),
  los dashboards con ECharts y la captura de firma de asistencia.
* Alpine.js evalúa ``x-data`` / ``@click`` con ``new Function()`` y el CDN de
  Tailwind compila CSS en el navegador: ambos exigen ``'unsafe-eval'``.
* Tailwind Play CDN inyecta ``<style>`` en runtime SIN nonce, y 35 templates
  usan atributos ``style="..."``: ambos exigen ``'unsafe-inline'`` en estilos.

OJO con los nonces: por spec, si una directiva trae un nonce el navegador
IGNORA ``'unsafe-inline'`` en esa misma directiva. Por eso acá NO se usa el
sentinel ``NONCE`` todavía — meterlo hoy invertiría el efecto y rompería los 24
templates sin nonce. El camino de salida es: (1) medir con report-only,
(2) ponerle nonce a los inline restantes, (3) recién ahí cambiar
``'unsafe-inline'`` por ``NONCE`` y encender ``CSP_ENFORCE``.

Orígenes: cada entrada de abajo sale de un ``grep`` sobre templates, no de un
template genérico. Ver el comentario de cada directiva.
"""

from csp.constants import NONE, SELF, UNSAFE_EVAL, UNSAFE_INLINE

# --- Orígenes de terceros efectivamente usados por los templates -------------
# grep -rhoE 'https?://[a-zA-Z0-9._-]+' --include='*.html' templates apps
# <script> en templates/base/base.html y apps/feedback/templates/feedback/base.html
CDN_TAILWIND = "https://cdn.tailwindcss.com"
# alpinejs@3.x.x, echarts@5.5.0, sortablejs@1.15.0 (js) + daisyui@4.10.1 (css)
CDN_JSDELIVR = "https://cdn.jsdelivr.net"
# htmx.org@1.9.11 / @1.9.12 + ext/loading-states
CDN_UNPKG = "https://unpkg.com"
# font-awesome@6.4.0 (CSS + woff2)
CDN_CLOUDFLARE = "https://cdnjs.cloudflare.com"

# Media servida por Google Cloud Storage. En Cloud Run el bucket es
# GS_BUCKET_NAME=sd-lms-media con GS_DEFAULT_ACL=publicRead y
# GS_QUERYSTRING_AUTH=False, así que las URLs quedan bajo storage.googleapis.com.
GCS = "https://storage.googleapis.com"

# Imágenes servidas por GitHub. El portal público de tickets
# (apps/feedback/) es un frente sobre issues de GitHub: services.py publica las
# URLs de los adjuntos en el issue y el portal renderiza de vuelta el markdown
# de los comentarios, cuyas imágenes las sirve GitHub desde estos hosts.
GITHUB_IMG = "https://*.githubusercontent.com"
GITHUB = "https://github.com"

# Reproductores de video embebidos por URL en las lecciones
# (templates/courses/lesson_view.html + partials/builder/lesson_form.html).
YOUTUBE = "https://www.youtube.com"
YOUTUBE_NOCOOKIE = "https://www.youtube-nocookie.com"
VIMEO = "https://player.vimeo.com"

DATA_URI = "data:"


# --- Política ----------------------------------------------------------------
# Nota: los valores son listas; django-csp 4.0 las une con espacios por
# directiva. Ver csp.utils.build_policy.
CSP_DIRECTIVES: dict[str, list[str]] = {
    "default-src": [SELF],
    # script-src: los 3 CDNs con <script src=...> + 'unsafe-eval' (Alpine
    # compila expresiones con new Function(); el CDN de Tailwind compila CSS en
    # el navegador) + 'unsafe-inline' por los 29 <script> inline (solo 10 con
    # nonce). NO agregar NONCE acá hasta que TODOS lleven nonce: el nonce anula
    # 'unsafe-inline'.
    "script-src": [
        SELF,
        UNSAFE_INLINE,
        UNSAFE_EVAL,
        CDN_TAILWIND,
        CDN_JSDELIVR,
        CDN_UNPKG,
    ],
    # 25 onclick="" + 4 onsubmit="" en templates. Los nonces NO aplican a
    # atributos: mientras existan, esto tiene que quedar en 'unsafe-inline'.
    "script-src-attr": [UNSAFE_INLINE],
    # style-src: daisyui (jsdelivr) + font-awesome (cdnjs). 'unsafe-inline' es
    # obligatorio porque Tailwind Play CDN inyecta <style> en runtime sin nonce.
    "style-src": [SELF, UNSAFE_INLINE, CDN_JSDELIVR, CDN_CLOUDFLARE],
    # 35 templates con atributo style="...".
    "style-src-attr": [UNSAFE_INLINE],
    # img-src: 'data:' es obligatorio — la firma de asistencia se dibuja en un
    # <canvas> y se vuelca con canvas.toDataURL('image/png') a un <img>
    # (templates/courses/attendance_lesson.html,
    # templates/preop_talks/partials/attendees_list.html).
    "img-src": [SELF, DATA_URI, GCS, GITHUB_IMG, GITHUB],
    "font-src": [SELF, CDN_CLOUDFLARE],
    # <video><source src="{{ lesson.content_file.url }}"> apunta a GCS.
    "media-src": [SELF, GCS],
    # OJO: 'none' rompería el visor de lecciones PDF, que usa
    # <object data="{% url 'courses:lesson_content_file' %}" type="application/pdf">
    # (mismo origen) en templates/courses/lesson_view.html.
    "object-src": [SELF],
    # iframes: video externo de las lecciones + el PDF del certificado servido
    # desde GCS (templates/certifications/certificate_detail.html).
    "frame-src": [SELF, GCS, YOUTUBE, YOUTUBE_NOCOOKIE, VIMEO],
    # htmx y fetch() solo pegan al mismo origen (no hay fetch a hosts externos).
    "connect-src": [SELF],
    # Coherente con X_FRAME_OPTIONS = "DENY" que ya trae cloudrun.py.
    "frame-ancestors": [NONE],
    "form-action": [SELF],
    "base-uri": [SELF],
}
