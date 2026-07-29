"""
Tests SD#76 -- el header de CSP se EMITE con el settings que corre en produccion.

Por que estos tests y no otros
------------------------------
El bug de #76 no era "la constante esta mal escrita": era que NADIE ejercitaba
el camino real. La CSP estaba declarada en `config/settings/production.py`, un
modulo que produccion no carga (deploy.yml despliega Cloud Run con
DJANGO_SETTINGS_MODULE=config.settings.cloudrun), y encima en el formato plano
CSP_* que django-csp 4.0 ignora en silencio. Un test que solo mirara "existe
CSP_SCRIPT_SRC en el archivo" habria pasado en verde con cero header en prod.

Ademas `config/settings/test.py` saca a proposito el CSPMiddleware del
MIDDLEWARE ("avoids django-csp version conflicts"), asi que la suite por
defecto nunca podia ver el header. Por eso aca:

  1. Se importa DE VERDAD el modulo de settings que despliega deploy.yml
     (no se copian los valores a mano).
  2. Se corre el CSPMiddleware real con esa configuracion y se afirma sobre el
     header de la respuesta, no sobre la constante.
  3. Se cubre tambien el request end-to-end por el stack de middleware de prod.

NOTA: a proposito NO se importa `config.settings.production` aca. Ese modulo
hace `INSTALLED_APPS += ["cachalot"]`, que muta in-place la lista compartida
con `config.settings.base` y contaminaria el resto de la suite. Para production
se valida a nivel de fuente (test_production_settings_migrado).
"""

import importlib
import os
import re
import sys
from contextlib import contextmanager
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from csp.checks import OUTDATED_SETTINGS
from csp.constants import HEADER, HEADER_REPORT_ONLY
from csp.middleware import CSPMiddleware

# El modulo que deploy.yml pasa como DJANGO_SETTINGS_MODULE al desplegar
# Cloud Run (y a los jobs de migrate / ensure_admin / axes_reset).
PROD_SETTINGS_MODULE = "config.settings.cloudrun"

# Minimo para poder importar el settings de Cloud Run fuera de Cloud Run:
# cloudrun.py resuelve config("DB_PASSWORD") sin default al importarse.
_REQUIRED_ENV = {"DB_PASSWORD": "solo-para-tests"}


@contextmanager
def load_prod_settings(**extra_env):
    """Importa de verdad el modulo de settings que corre en produccion.

    Se importa como modulo (no se activa como settings de Django) para poder
    leer sus valores reales sin tocar la configuracion viva de la suite.
    """
    env = {**_REQUIRED_ENV, **extra_env}
    previous = {key: os.environ.get(key) for key in env}
    os.environ.update(env)
    sys.modules.pop(PROD_SETTINGS_MODULE, None)
    try:
        yield importlib.import_module(PROD_SETTINGS_MODULE)
    finally:
        sys.modules.pop(PROD_SETTINGS_MODULE, None)
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def run_middleware(**settings_overrides):
    """Corre el CSPMiddleware real sobre una respuesta cualquiera."""
    with override_settings(**settings_overrides):
        middleware = CSPMiddleware(lambda request: HttpResponse("ok"))
        return middleware(RequestFactory().get("/"))


class ProdSettingsDefineCSPTests(SimpleTestCase):
    """El settings que realmente corre en prod define la politica (fact #1)."""

    def test_cloudrun_define_la_politica_en_formato_django_csp_4(self):
        with load_prod_settings() as prod:
            # Default = report-only: emite y reporta, no bloquea.
            self.assertTrue(
                hasattr(prod, "CONTENT_SECURITY_POLICY_REPORT_ONLY"),
                "config.settings.cloudrun no define CONTENT_SECURITY_POLICY_REPORT_ONLY; "
                "produccion volveria a quedarse sin header (SD#76).",
            )
            policy = prod.CONTENT_SECURITY_POLICY_REPORT_ONLY
            self.assertIn("DIRECTIVES", policy)
            self.assertIn("default-src", policy["DIRECTIVES"])

    def test_cloudrun_no_conserva_settings_planos_csp_legacy(self):
        """Las CSP_* planas son ignoradas en silencio por django-csp 4.0."""
        with load_prod_settings() as prod:
            sobrevivientes = [name for name in OUTDATED_SETTINGS if hasattr(prod, name)]
            self.assertEqual(
                sobrevivientes,
                [],
                f"Settings CSP legacy en {PROD_SETTINGS_MODULE}: {sobrevivientes}. "
                "django-csp 4.0 no las lee para construir la politica (solo dispara "
                "el check csp.E001).",
            )

    def test_csp_enforce_no_colisiona_con_el_namespace_legacy(self):
        """Guarda: si una version futura reclama CSP_ENFORCE, que salte aca."""
        self.assertNotIn("CSP_ENFORCE", OUTDATED_SETTINGS)

    def test_app_csp_instalada_para_que_sus_checks_se_registren(self):
        """Tercera capa de silencio de SD#76.

        Los checks de django-csp (csp.E001 "estas usando settings < 4.0") se
        registran desde csp/apps.py. Sin "csp" en INSTALLED_APPS el formato
        viejo no producia NI header NI aviso. Con la app instalada, volver al
        formato plano rompe `manage.py check`.
        """
        self.assertIn("csp", settings.INSTALLED_APPS)

    def test_el_check_de_django_csp_detecta_el_formato_viejo(self):
        from csp.checks import check_django_csp_lt_4_0

        self.assertEqual(check_django_csp_lt_4_0(None), [])

        with override_settings(CSP_DEFAULT_SRC=["'self'"]):
            errores = check_django_csp_lt_4_0(None)
        self.assertEqual([e.id for e in errores], ["csp.E001"])


class CSPHeaderSeEmiteTests(SimpleTestCase):
    """El header SALE. Este es el test que habria atrapado SD#76."""

    def test_header_report_only_se_emite_con_la_politica_de_produccion(self):
        with load_prod_settings() as prod:
            policy = prod.CONTENT_SECURITY_POLICY_REPORT_ONLY

        response = run_middleware(CONTENT_SECURITY_POLICY_REPORT_ONLY=policy)

        self.assertIn(
            HEADER_REPORT_ONLY,
            response,
            "El CSPMiddleware no emitio Content-Security-Policy-Report-Only con la "
            "configuracion real de produccion.",
        )
        header = response[HEADER_REPORT_ONLY]
        self.assertTrue(header.strip(), "El header salio vacio.")
        self.assertIn("default-src 'self'", header)
        # Arranca en report-only: NO debe salir el header bloqueante.
        self.assertNotIn(HEADER, response)

    def test_con_csp_enforce_el_header_pasa_a_bloqueante(self):
        with load_prod_settings(CSP_ENFORCE="True") as prod:
            self.assertTrue(
                hasattr(prod, "CONTENT_SECURITY_POLICY"),
                "Con CSP_ENFORCE=True cloudrun.py debe definir CONTENT_SECURITY_POLICY.",
            )
            self.assertFalse(hasattr(prod, "CONTENT_SECURITY_POLICY_REPORT_ONLY"))
            policy = prod.CONTENT_SECURITY_POLICY

        response = run_middleware(CONTENT_SECURITY_POLICY=policy)

        self.assertIn(HEADER, response)
        self.assertIn("default-src 'self'", response[HEADER])

    def test_el_formato_viejo_csp_plano_NO_emite_header(self):
        """Fija la causa raiz de SD#76: el formato < 4.0 se ignora en silencio."""
        response = run_middleware(
            CSP_DEFAULT_SRC=("'self'",),
            CSP_SCRIPT_SRC=("'self'", "cdn.jsdelivr.net"),
        )
        self.assertNotIn(HEADER, response)
        self.assertNotIn(HEADER_REPORT_ONLY, response)


class CSPHeaderEnRequestRealTests(TestCase):
    """End-to-end: request HTTP por el stack de middleware de produccion."""

    def test_health_check_responde_con_el_header_csp(self):
        with load_prod_settings() as prod:
            prod_middleware = list(prod.MIDDLEWARE)
            policy = prod.CONTENT_SECURITY_POLICY_REPORT_ONLY

        self.assertIn(
            "csp.middleware.CSPMiddleware",
            prod_middleware,
            "El MIDDLEWARE de produccion perdio el CSPMiddleware.",
        )

        with override_settings(
            MIDDLEWARE=prod_middleware,
            CONTENT_SECURITY_POLICY_REPORT_ONLY=policy,
        ):
            response = self.client.get("/health/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(HEADER_REPORT_ONLY, response)
        self.assertIn("default-src 'self'", response[HEADER_REPORT_ONLY])


class PoliticaCubreLosOrigenesRealesTests(SimpleTestCase):
    """La politica se armo sobre los origenes que la app usa de verdad.

    Cada afirmacion corresponde a evidencia concreta en templates. Si alguien
    "endurece" la CSP sacando uno de estos, rompe una pantalla en produccion de
    forma dificil de diagnosticar (no hay error de servidor, la pagina queda a
    medias). Estos asserts son el recordatorio.
    """

    maxDiff = None

    def setUp(self):
        with load_prod_settings() as prod:
            self.directives = prod.CONTENT_SECURITY_POLICY_REPORT_ONLY["DIRECTIVES"]

    def test_script_src_cubre_los_cdn_con_script_tag(self):
        script_src = self.directives["script-src"]
        # base/base.html + feedback/base.html
        self.assertIn("https://cdn.tailwindcss.com", script_src)
        # alpinejs@3.x.x, echarts@5.5.0, sortablejs@1.15.0
        self.assertIn("https://cdn.jsdelivr.net", script_src)
        # htmx.org@1.9.11 / @1.9.12 + ext/loading-states
        self.assertIn("https://unpkg.com", script_src)

    def test_script_src_permite_eval_por_alpine_y_tailwind_cdn(self):
        """Alpine evalua x-data/@click con new Function(); Tailwind CDN compila CSS."""
        self.assertIn("'unsafe-eval'", self.directives["script-src"])

    def test_script_src_no_mezcla_nonce_con_unsafe_inline(self):
        """Un nonce hace que el navegador IGNORE 'unsafe-inline' en esa directiva.

        Quedan 29 bloques <script> inline y solo 10 llevan nonce, asi que meter
        el nonce hoy apagaria 'unsafe-inline' y romperia los otros 19 (portal
        publico de tickets, dashboards con ECharts, firma de asistencia).
        """
        script_src = self.directives["script-src"]
        self.assertIn("'unsafe-inline'", script_src)
        self.assertFalse(
            any("nonce" in str(value) for value in script_src),
            "script-src mezcla nonce con 'unsafe-inline': el nonce gana y anula "
            "el 'unsafe-inline' del que dependen los inline sin nonce.",
        )

    def test_style_src_permite_inline_por_el_cdn_de_tailwind(self):
        """Tailwind Play CDN inyecta <style> en runtime, sin nonce posible."""
        style_src = self.directives["style-src"]
        self.assertIn("'unsafe-inline'", style_src)
        self.assertIn("https://cdn.jsdelivr.net", style_src)  # daisyui@4.10.1
        self.assertIn("https://cdnjs.cloudflare.com", style_src)  # font-awesome@6.4.0

    def test_img_src_cubre_data_uri_gcs_y_github(self):
        img_src = self.directives["img-src"]
        # canvas.toDataURL('image/png') de la firma de asistencia
        self.assertIn("data:", img_src)
        # media del bucket sd-lms-media (publicRead, sin querystring auth)
        self.assertIn("https://storage.googleapis.com", img_src)
        # portal publico de tickets, montado sobre issues de GitHub
        self.assertIn("https://*.githubusercontent.com", img_src)

    def test_media_src_cubre_los_videos_de_leccion_en_gcs(self):
        self.assertIn("https://storage.googleapis.com", self.directives["media-src"])

    def test_object_src_no_es_none_porque_hay_visor_pdf(self):
        """lesson_view.html usa <object type="application/pdf"> del mismo origen."""
        self.assertEqual(self.directives["object-src"], ["'self'"])

    def test_frame_src_cubre_video_externo_y_certificado_en_gcs(self):
        frame_src = self.directives["frame-src"]
        self.assertIn("https://www.youtube.com", frame_src)
        self.assertIn("https://www.youtube-nocookie.com", frame_src)
        self.assertIn("https://player.vimeo.com", frame_src)
        # certificate_detail.html embebe el PDF del certificado servido por GCS
        self.assertIn("https://storage.googleapis.com", frame_src)

    def test_clickjacking_coherente_con_x_frame_options(self):
        self.assertEqual(self.directives["frame-ancestors"], ["'none'"])


class ProductionSettingsMigradoTests(SimpleTestCase):
    """production.py tambien quedo migrado (no se despliega, pero no debe mentir).

    Se valida por fuente: importarlo tiene efectos colaterales (muta
    INSTALLED_APPS in-place, ver docstring del modulo).
    """

    def test_production_no_conserva_asignaciones_csp_planas(self):
        ruta = Path(settings.BASE_DIR) / "config" / "settings" / "production.py"
        fuente = ruta.read_text(encoding="utf-8")
        legacy = [
            name
            for name in OUTDATED_SETTINGS + ["CSP_INCLUDE_NONCE_IN"]
            if re.search(rf"^{name}\s*=", fuente, flags=re.MULTILINE)
        ]
        self.assertEqual(
            legacy,
            [],
            f"config/settings/production.py todavia asigna settings CSP legacy: {legacy}",
        )

    def test_production_usa_la_politica_compartida(self):
        ruta = Path(settings.BASE_DIR) / "config" / "settings" / "production.py"
        fuente = ruta.read_text(encoding="utf-8")
        self.assertIn("from .csp import CSP_DIRECTIVES", fuente)
