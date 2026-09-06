"""
Tests for SD#136 -- video-lesson "AMBI" quedaba con candado indefinidamente
para leccion de video EXTERNO (video_url, embed de YouTube).

Causa raiz (F2_OUTPUT.causa_raiz_confirmada): externalVideoTracker()
(templates/courses/lesson_view.html) usaba un reloj de pared del lado
cliente -- `elapsed += 1s` por tick de `setInterval` mientras la pestana
esta abierta -- comparado contra `totalDuration = lesson.duration * 60`
(duracion ESTIMADA en minutos, cargada a mano por el autor del curso) para
decidir cuando el video "termino" (umbral 95%). Para la leccion real (id=507,
'SST'/'Politica de Seguridad Vial', curso 472), duration=2 (120s) fue
cargado a mano pero el video real dura 37s -> el gate exigia ~114s de
PESTANA ABIERTA, es decir ~77s MAS de espera pasiva tras el fin visual del
video, sin ninguna senal en la UI. Reproducido con datos reales: usuaria
Angie Pamela Galeano Villamizar (lesson_progress id=321) is_completed=false,
progress_percent=0.83% pese a haber visto el video completo.

Fix (F2_OUTPUT.fix_propuesto, un solo archivo,
templates/courses/lesson_view.html): reemplazar el reloj de pared por la
YouTube IFrame API -- el src del iframe gana `enablejsapi=1` + un `id`
unico por leccion (`yt-player-{{ lesson.id }}`), se carga
`https://www.youtube.com/iframe_api` una sola vez, y `externalVideoTracker()`
se reescribe para instanciar `YT.Player` sobre ese iframe y escuchar
`onStateChange` (ENDED -> `sendProgress(true)` con `player.getDuration()`
REAL, no `lesson.duration*60`). El backend (update_video_progress) NO
cambia -- F2 lo verifico correcto.

Django's test client NO ejecuta JS (Alpine, la IFrame API real, postMessage
entre iframes), asi que estos tests validan lo que SI es observable sin
navegador: que el HTML renderizado trae el wiring correcto para que el fix
de JS pueda enganchar (enablejsapi=1, id del iframe, script de la IFrame
API), y que el reproductor de `content_file` (HTML5 nativo, ruta separada
que el fix NO debe tocar) sigue renderizando igual que antes.

El comportamiento end-to-end real (gate se desbloquea con progreso REAL del
reproductor) esta cubierto por el journey E2E mutativo
`SPRINTS/RUN_2026-08-14_2002/journeys/SD_136.yaml`, que simula el payload
exacto que la IFrame API envia al terminar el video (duration=largo real,
no una estimacion) contra el mismo endpoint `update_video_progress`.
"""

from datetime import date

from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.courses.models import Category, Course, Enrollment, Lesson, Module

_SEQ = [13600]


def _next_seq():
    _SEQ[0] += 1
    return _SEQ[0]


def _make_user(**overrides):
    n = _next_seq()
    defaults = {
        "email": f"issue136_user_{n}@test.com",
        "password": "testpass123",
        "first_name": f"User{n}",
        "last_name": "SD136",
        "document_number": f"8{n:08d}",
        "job_position": "Tech",
        "hire_date": date(2024, 1, 1),
    }
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


def _make_course_and_module(creator):
    n = _next_seq()
    category = Category.objects.create(
        name=f"Cat SD136 {n}", slug=f"cat-sd136-{n}", description="c", color="#3B82F6"
    )
    course = Course.objects.create(
        code=f"ISSUE136-{n}",
        title=f"Curso SD136 {n}",
        description="desc",
        objectives="obj",
        course_type=Course.Type.MANDATORY,
        status=Course.Status.PUBLISHED,
        category=category,
        created_by=creator,
    )
    module = Module.objects.create(course=course, title="M1", description="d", order=0)
    return course, module


class ExternalVideoLessonIframeWiringTests(TestCase):
    """La leccion de video EXTERNO (video_url, sin content_file) debe traer
    el wiring que el fix de JS necesita para enganchar la YouTube IFrame
    API: enablejsapi=1 en el src, un id unico, y el script de la API."""

    def setUp(self):
        self.client = Client()
        self.creator = _make_user()
        self.student = _make_user()
        self.course, self.module = _make_course_and_module(self.creator)

        # Mismo shape que la leccion real 507 del cliente: duration=2 min
        # (estimacion a mano) mientras el video real dura ~37s -- esto es
        # justo lo que rompia el reloj de pared viejo.
        self.video_lesson = Lesson.objects.create(
            module=self.module,
            title="SST - Politica de Seguridad Vial",
            lesson_type=Lesson.Type.VIDEO,
            video_url="https://www.youtube.com/watch?v=fPaZMO6k4mc",
            duration=2,
            order=0,
            is_mandatory=True,
        )
        self.enrollment = Enrollment.objects.create(user=self.student, course=self.course)
        self.lesson_url = reverse("courses:lesson", args=[self.course.id, self.video_lesson.id])

    def test_iframe_src_includes_enablejsapi(self):
        """SD#136 core fix: sin enablejsapi=1 la YouTube IFrame API no puede
        adjuntar un YT.Player sobre el iframe existente (requisito documentado
        de la API de YouTube)."""
        self.client.force_login(self.student)
        resp = self.client.get(self.lesson_url)
        self.assertEqual(resp.status_code, 200)
        # El modelo normaliza cualquier URL de YouTube a la forma
        # https://www.youtube.com/embed/<id> (Lesson.save() ->
        # convert_youtube_url_to_embed), asi que el src debe verse con
        # exactamente un "?" seguido de enablejsapi=1.
        self.video_lesson.refresh_from_db()
        self.assertEqual(self.video_lesson.video_url, "https://www.youtube.com/embed/fPaZMO6k4mc")
        self.assertContains(
            resp,
            'src="https://www.youtube.com/embed/fPaZMO6k4mc?enablejsapi=1',
        )

    def test_iframe_has_unique_id_per_lesson(self):
        """externalVideoTracker() adjunta YT.Player pasandole este id -- sin
        el id correcto (`yt-player-{{ lesson.id }}`), new YT.Player(id) no
        encuentra el elemento y el fix entero queda mudo."""
        self.client.force_login(self.student)
        resp = self.client.get(self.lesson_url)
        self.assertContains(resp, f'id="yt-player-{self.video_lesson.id}"')

    def test_youtube_iframe_api_script_is_loaded(self):
        """El script oficial de la API debe cargarse para que
        `window.YT.Player` exista en el navegador."""
        self.client.force_login(self.student)
        resp = self.client.get(self.lesson_url)
        self.assertContains(resp, "https://www.youtube.com/iframe_api")

    def test_external_video_tracker_no_longer_uses_wall_clock_as_primary_signal(self):
        """Regresion negativa del bug original: el codigo ya NO debe
        incrementar `elapsed` ciegamente en cada tick de setInterval como
        UNICA senal de fin de video -- eso es exactamente lo que hacia que
        el umbral de 95% fuera inalcanzable cuando `lesson.duration` (una
        estimacion a mano) era mayor a la duracion real. La nueva version
        debe reaccionar a `onStateChange`/`YT.PlayerState.ENDED`, la senal
        REAL del reproductor."""
        self.client.force_login(self.student)
        resp = self.client.get(self.lesson_url)
        content = resp.content.decode()
        self.assertIn("onStateChange", content)
        self.assertIn("YT.PlayerState.ENDED", content)
        self.assertIn("getDuration", content)
        # El fallback de reloj de pared sigue existiendo (degradacion
        # controlada si la API no carga), pero ya NO es el UNICO camino de
        # deteccion de fin de video -- debe convivir con el tracking real.
        self.assertIn("_startWallClockFallback", content)

    def test_duration_zero_does_not_crash_render(self):
        """Edge case: leccion de video sin `duration` configurado (0, el
        default del modelo). El fix no debe depender de que el autor haya
        cargado una duracion para renderizar sin errores -- la duracion
        real ahora la aporta el reproductor, no el campo manual.

        Curso/modulo/enrollment propios (en vez de reusar self.module) para
        que la leccion quede en indice 0 y sea accesible sin depender de
        completar otra leccion previa (is_lesson_accessible)."""
        course2, module2 = _make_course_and_module(self.creator)
        lesson = Lesson.objects.create(
            module=module2,
            title="Video sin duracion cargada",
            lesson_type=Lesson.Type.VIDEO,
            video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            duration=0,
            order=0,
            is_mandatory=False,
        )
        Enrollment.objects.create(user=self.student, course=course2)
        self.client.force_login(self.student)
        url = reverse("courses:lesson", args=[course2.id, lesson.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f'id="yt-player-{lesson.id}"')


class ContentFileVideoPlayerNoRegressionTests(TestCase):
    """La leccion de video con `content_file` (HTML5 nativo, `videoPlayer()`)
    es una ruta completamente separada que el fix de SD#136 NO debe tocar --
    debe seguir renderizando exactamente igual que antes."""

    def setUp(self):
        self.client = Client()
        self.creator = _make_user()
        self.student = _make_user()
        self.course, self.module = _make_course_and_module(self.creator)

        from django.core.files.uploadedfile import SimpleUploadedFile

        self.video_lesson = Lesson.objects.create(
            module=self.module,
            title="Video HTML5 nativo",
            lesson_type=Lesson.Type.VIDEO,
            content_file=SimpleUploadedFile(
                "clip.mp4", b"fake-mp4-bytes", content_type="video/mp4"
            ),
            duration=5,
            order=0,
            is_mandatory=True,
        )
        self.enrollment = Enrollment.objects.create(user=self.student, course=self.course)
        self.lesson_url = reverse("courses:lesson", args=[self.course.id, self.video_lesson.id])

    def test_html5_video_player_still_renders(self):
        self.client.force_login(self.student)
        resp = self.client.get(self.lesson_url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'x-data="videoPlayer()"')
        self.assertContains(resp, '@ended="onEnded()"')

    def test_html5_video_player_does_not_use_external_tracker_wiring(self):
        """No-regresion: una leccion con `content_file` no debe caer por la
        rama de `externalVideoTracker()` ni traer el wiring nuevo de
        enablejsapi/YouTube (esa rama es exclusiva de `lesson.video_url` sin
        `content_file`, ver el `{% if lesson.content_file %}...{% elif
        lesson.video_url %}` de lesson_view.html). Nota: la DEFINICION de
        `Alpine.data('externalVideoTracker', ...)` (incluyendo su string JS
        interno `_iframeId: "yt-player-<id>"`) vive en el mismo `<script>`
        compartido que se emite para TODA leccion `lesson_type == 'video'`
        (pre-existente, no cambia con este fix) -- lo que NO debe aparecer
        es el DOM real que lo activa: `x-data="externalVideoTracker()"`,
        el atributo `id="yt-player-..."` de un iframe, ni el iframe mismo."""
        self.client.force_login(self.student)
        resp = self.client.get(self.lesson_url)
        content = resp.content.decode()
        self.assertNotIn('x-data="externalVideoTracker()"', content)
        self.assertNotIn("enablejsapi", content)
        self.assertNotIn('id="yt-player-', content)
        self.assertNotIn("<iframe", content)
