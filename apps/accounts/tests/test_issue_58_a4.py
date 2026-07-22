"""Tests for la utilidad de gating RBAC `apps.accounts.permissions` (SD#58, A4).

Cubre:
  - Unit tests puros de `user_has_rol()` (anónimo, rol=None, rol correcto,
    rol incorrecto, múltiples roles admitidos).
  - `require_rol()` en sus 3 modos (redirect+mensaje default, `json_only`,
    `raise_exception`) y su validación de configuración (`ValueError` si no
    hay `redirect_url` ni modo alternativo).
  - `RolRequiredMixin` sobre una CBV mínima construida en el propio test
    (ninguna vista real del issue #58 es CBV — ver docstring del módulo).
  - Regresión de integración: representantes reales de los archivos que A4
    migró de `is_staff` a `rol` (`accounts`, `courses`, `certifications`,
    `preop_talks`, `lessons_learned`, `reports`, `gamification`) — un
    ADMINISTRADOR sigue pasando, un EJECUTOR (y en los gates admin-only, un
    COORDINADOR) queda bloqueado. (`attendance` migró en su momento pero el
    módulo se borró completo en issue #64, reemplazado por
    `apps.courses.AttendanceSignature` #63 — sus tests representantes se
    quitaron de aquí y de `test_issue_58_a8.py`.)
  - Regresión "legacy": un usuario con `is_staff=True` pero `rol=None`
    (estado real de cualquier fila existente en producción entre el deploy
    de A1 y que corra el backfill, o cualquier fixture de test antigua que
    no haya sido actualizada) YA NO tiene acceso — prueba que `is_staff`
    dejó de ser fuente de verdad (decisión de Miguel #2 del PLAN).
"""

import itertools
from datetime import date, datetime, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.views import View

from apps.accounts.permissions import Rol, RolRequiredMixin, require_rol, user_has_rol
from apps.lessons_learned.models import Category as LessonCategory
from apps.lessons_learned.models import LessonLearned
from apps.preop_talks.models import PreopTalk

User = get_user_model()

_SEQ = itertools.count(1)


def _make_user(rol=None, is_staff=False, **overrides):
    n = next(_SEQ)
    defaults = {
        "email": f"a4_user_{n}@example.com",
        "password": "testpass123",
        "first_name": f"User{n}",
        "last_name": "A4",
        "document_type": "CC",
        "document_number": f"70{n:07d}",
        "job_position": "Tech",
        "job_profile": None,
        "hire_date": date(2024, 1, 1),
        "is_staff": is_staff,
        "rol": rol,
    }
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


class UserHasRolTests(TestCase):
    """Unit tests puros de `user_has_rol()` — no toca la BD salvo crear el user."""

    def test_administrador_pasa_su_propio_check(self):
        user = _make_user(rol=Rol.ADMINISTRADOR)
        self.assertTrue(user_has_rol(user, Rol.ADMINISTRADOR))

    def test_ejecutor_no_pasa_check_administrador(self):
        user = _make_user(rol=Rol.EJECUTOR)
        self.assertFalse(user_has_rol(user, Rol.ADMINISTRADOR))

    def test_multiples_roles_admitidos_or(self):
        coordinador = _make_user(rol=Rol.COORDINADOR)
        self.assertTrue(user_has_rol(coordinador, Rol.ADMINISTRADOR, Rol.COORDINADOR))
        ejecutor = _make_user(rol=Rol.EJECUTOR)
        self.assertFalse(user_has_rol(ejecutor, Rol.ADMINISTRADOR, Rol.COORDINADOR))

    def test_rol_none_no_otorga_permisos_elevados(self):
        """Bucket 'sin asignar' del backfill de A1 -> sin acceso, no default adivinado."""
        user = _make_user(rol=None)
        self.assertFalse(user_has_rol(user, Rol.ADMINISTRADOR))
        self.assertFalse(user_has_rol(user, Rol.EJECUTOR, Rol.COORDINADOR, Rol.ADMINISTRADOR))

    def test_usuario_anonimo_false(self):
        from django.contrib.auth.models import AnonymousUser

        self.assertFalse(user_has_rol(AnonymousUser(), Rol.ADMINISTRADOR))

    def test_is_staff_solo_ya_no_alcanza(self):
        """Regresión central de A4: is_staff=True sin `rol` NO otorga acceso."""
        user = _make_user(rol=None, is_staff=True, is_superuser=True)
        self.assertFalse(user_has_rol(user, Rol.ADMINISTRADOR))


class RequireRolDecoratorTests(TestCase):
    """`require_rol()` en sus 3 modos, con requests sintéticos (RequestFactory)."""

    def setUp(self):
        self.factory = RequestFactory()

    def _add_session_and_messages(self, request):
        # messages.error necesita middleware de sesión/mensajes montado.
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.middleware import SessionMiddleware

        SessionMiddleware(lambda r: None).process_request(request)
        request.session.save()
        request._messages = FallbackStorage(request)
        return request

    def test_redirect_mode_allows_matching_rol(self):
        @require_rol(Rol.ADMINISTRADOR, redirect_url="accounts:dashboard")
        def view(request):
            return HttpResponse("ok")

        request = self._add_session_and_messages(self.factory.get("/x"))
        request.user = _make_user(rol=Rol.ADMINISTRADOR)
        response = view(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")

    def test_redirect_mode_blocks_and_sets_message(self):
        @require_rol(Rol.ADMINISTRADOR, redirect_url="accounts:dashboard", message="Nope")
        def view(request):
            return HttpResponse("ok")

        request = self._add_session_and_messages(self.factory.get("/x"))
        request.user = _make_user(rol=Rol.EJECUTOR)
        response = view(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:dashboard"))
        messages = [str(m) for m in get_messages(request)]
        self.assertIn("Nope", messages)

    def test_json_only_mode_always_json_403_no_message_no_redirect(self):
        @require_rol(Rol.ADMINISTRADOR, json_only=True)
        def view(request):
            return HttpResponse("ok")

        request = self.factory.post("/x")
        request.user = _make_user(rol=Rol.EJECUTOR)
        response = view(request)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response["Content-Type"], "application/json")

    def test_raise_exception_mode_raises_permission_denied(self):
        @require_rol(Rol.ADMINISTRADOR, raise_exception=True)
        def view(request):
            return HttpResponse("ok")

        request = self.factory.get("/x")
        request.user = _make_user(rol=Rol.COORDINADOR)
        with self.assertRaises(PermissionDenied):
            view(request)

    def test_misconfigured_decorator_raises_valueerror_at_definition_time(self):
        """Sin redirect_url ni json_only/raise_exception -> error temprano,
        no un fallo silencioso en runtime."""
        with self.assertRaises(ValueError):
            require_rol(Rol.ADMINISTRADOR)


class RolRequiredMixinTests(TestCase):
    """`RolRequiredMixin` sobre una CBV mínima (ninguna vista real la usa
    todavía — ver Nota del módulo `permissions.py`), para que A5-A10 tengan
    la garantía de que el mixin funciona antes de adoptarlo."""

    def test_mixin_allows_matching_rol(self):
        class _AdminOnlyView(RolRequiredMixin, View):
            allowed_roles = (Rol.ADMINISTRADOR,)
            redirect_url = "accounts:dashboard"

            def get(self, request):
                return HttpResponse("ok")

        request = RequestFactory().get("/x")
        request.user = _make_user(rol=Rol.ADMINISTRADOR)
        response = _AdminOnlyView.as_view()(request)
        self.assertEqual(response.status_code, 200)

    def test_mixin_blocks_and_redirects_when_configured(self):
        class _AdminOnlyView(RolRequiredMixin, View):
            allowed_roles = (Rol.ADMINISTRADOR,)
            redirect_url = "accounts:dashboard"

            def get(self, request):
                return HttpResponse("ok")

        request = RequestFactory().get("/x")
        request.user = _make_user(rol=Rol.EJECUTOR)
        # messages.error necesita storage montado
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.middleware import SessionMiddleware

        SessionMiddleware(lambda r: None).process_request(request)
        request.session.save()
        request._messages = FallbackStorage(request)

        response = _AdminOnlyView.as_view()(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:dashboard"))

    def test_mixin_raises_permission_denied_without_redirect_url(self):
        class _AdminOnlyViewNoRedirect(RolRequiredMixin, View):
            allowed_roles = (Rol.ADMINISTRADOR,)

            def get(self, request):
                return HttpResponse("ok")

        request = RequestFactory().get("/x")
        request.user = _make_user(rol=Rol.EJECUTOR)
        with self.assertRaises(PermissionDenied):
            _AdminOnlyViewNoRedirect.as_view()(request)


class MigratedViewsRegressionTests(TestCase):
    """Integración end-to-end (test Client real) sobre UN representante de
    cada uno de los 8 archivos migrados por A4. Prueba que el gate real de
    la vista lee `rol` — no `is_staff` ni `job_profile` — y que un
    ADMINISTRADOR backfillado (is_staff=True Y rol=ADMINISTRADOR, tal como
    deja la migración 0016 de A1) sigue teniendo acceso igual que antes."""

    def setUp(self):
        self.client = Client()
        self.administrador = _make_user(rol=Rol.ADMINISTRADOR, is_staff=True)
        self.coordinador = _make_user(rol=Rol.COORDINADOR)
        self.ejecutor = _make_user(rol=Rol.EJECUTOR)
        # "Legacy": is_staff=True pero SIN rol asignado (ej. fila de
        # producción entre el deploy de A1 y que corra el backfill 0016, o
        # cualquier fixture vieja no actualizada). Regresión central de A4.
        self.legacy_staff_sin_rol = _make_user(rol=None, is_staff=True, is_superuser=True)

    # --- 1. accounts/views.py — decorator require_rol ------------------

    def test_accounts_user_list_administrador_ok(self):
        self.client.force_login(self.administrador)
        response = self.client.get(reverse("accounts:user_list"))
        self.assertEqual(response.status_code, 200)

    def test_accounts_user_list_ejecutor_bloqueado(self):
        self.client.force_login(self.ejecutor)
        response = self.client.get(reverse("accounts:user_list"))
        self.assertRedirects(response, reverse("accounts:dashboard"))

    def test_accounts_user_list_legacy_staff_sin_rol_bloqueado(self):
        """Regresión: is_staff=True YA NO alcanza sin `rol=ADMINISTRADOR`."""
        self.client.force_login(self.legacy_staff_sin_rol)
        response = self.client.get(reverse("accounts:user_list"))
        self.assertRedirects(response, reverse("accounts:dashboard"))

    # --- 2. courses/views.py — decorator Y helper _staff_required -------

    def test_courses_category_list_administrador_ok(self):
        self.client.force_login(self.administrador)
        response = self.client.get(reverse("courses:category_list"))
        self.assertEqual(response.status_code, 200)

    def test_courses_category_list_coordinador_bloqueado(self):
        """El gate migrado es ADMINISTRADOR-only (equivalente exacto de
        is_staff) — A4 NO amplía el acceso a COORDINADOR, eso es scope de
        A5-A10 si aplica."""
        self.client.force_login(self.coordinador)
        response = self.client.get(reverse("courses:category_list"))
        self.assertRedirects(response, reverse("courses:list"))

    def test_courses_staff_required_helper_ejecutor_bloqueado(self):
        """`_staff_required()` (helper local reusado por ~19 vistas del
        builder) ahora lee `rol` via `user_has_rol`."""
        from apps.courses.models import Category, Course

        category = Category.objects.create(name="Cat A4", slug="cat-a4")
        course = Course.objects.create(
            code="A4-COURSE-1",
            title="Curso A4",
            description="d",
            objectives="o",
            category=category,
            course_type=Course.Type.MANDATORY,
            created_by=self.administrador,
        )
        self.client.force_login(self.ejecutor)
        response = self.client.get(
            reverse("courses:course_builder", kwargs={"course_id": course.id})
        )
        self.assertRedirects(response, reverse("courses:list"))

    # --- 3. certifications/views.py — decorator-generator user_passes_test

    def test_certifications_template_list_administrador_ok(self):
        self.client.force_login(self.administrador)
        response = self.client.get(reverse("certifications:template_list"))
        self.assertEqual(response.status_code, 200)

    def test_certifications_template_list_ejecutor_bloqueado(self):
        self.client.force_login(self.ejecutor)
        response = self.client.get(reverse("certifications:template_list"))
        self.assertEqual(response.status_code, 302)

    # --- 4. preop_talks/views.py — ownership bypass ----------------------

    def test_preop_talks_conduct_administrador_no_dueno_ok(self):
        talk = PreopTalk.objects.create(
            title="Charla A4",
            content="contenido",
            project_name="Proyecto A4",
            location="Sitio A4",
            work_activity="Actividad A4",
            scheduled_at=datetime(2024, 1, 1, 8, 0, tzinfo=dt_timezone.utc),
            conducted_by=self.ejecutor,
        )
        self.client.force_login(self.administrador)
        response = self.client.get(reverse("preop_talks:conduct", kwargs={"talk_id": talk.id}))
        self.assertEqual(response.status_code, 200)

    def test_preop_talks_conduct_otro_ejecutor_bloqueado(self):
        talk = PreopTalk.objects.create(
            title="Charla A4 B",
            content="contenido",
            project_name="Proyecto A4",
            location="Sitio A4",
            work_activity="Actividad A4",
            scheduled_at=datetime(2024, 1, 1, 8, 0, tzinfo=dt_timezone.utc),
            conducted_by=self.ejecutor,
        )
        otro_ejecutor = _make_user(rol=Rol.EJECUTOR)
        self.client.force_login(otro_ejecutor)
        response = self.client.get(reverse("preop_talks:conduct", kwargs={"talk_id": talk.id}))
        self.assertRedirects(response, reverse("preop_talks:detail", kwargs={"talk_id": talk.id}))

    # --- 5. lessons_learned/views.py — ownership bypass + gate puro ------

    def test_lessons_learned_edit_administrador_no_dueno_ok(self):
        category = LessonCategory.objects.create(name="Cat Lecciones A4")
        lesson = LessonLearned.objects.create(
            title="Leccion A4",
            description="desc",
            category=category,
            situation="situacion",
            lesson="leccion",
            recommendations="recomendaciones",
            created_by=self.ejecutor,
        )
        self.client.force_login(self.administrador)
        response = self.client.get(reverse("lessons_learned:edit", kwargs={"lesson_id": lesson.id}))
        self.assertEqual(response.status_code, 200)

    def test_lessons_learned_edit_otro_ejecutor_bloqueado(self):
        category = LessonCategory.objects.create(name="Cat Lecciones A4 B")
        lesson = LessonLearned.objects.create(
            title="Leccion A4 B",
            description="desc",
            category=category,
            situation="situacion",
            lesson="leccion",
            recommendations="recomendaciones",
            created_by=self.ejecutor,
        )
        otro_ejecutor = _make_user(rol=Rol.EJECUTOR)
        self.client.force_login(otro_ejecutor)
        response = self.client.get(reverse("lessons_learned:edit", kwargs={"lesson_id": lesson.id}))
        self.assertRedirects(
            response, reverse("lessons_learned:detail", kwargs={"lesson_id": lesson.id})
        )

    def test_lessons_learned_approve_ejecutor_bloqueado_403(self):
        category = LessonCategory.objects.create(name="Cat Lecciones A4 C")
        lesson = LessonLearned.objects.create(
            title="Leccion A4 C",
            description="desc",
            category=category,
            situation="situacion",
            lesson="leccion",
            recommendations="recomendaciones",
            created_by=self.ejecutor,
        )
        self.client.force_login(self.ejecutor)
        response = self.client.post(
            reverse("lessons_learned:approve", kwargs={"lesson_id": lesson.id})
        )
        self.assertEqual(response.status_code, 403)

    def test_lessons_learned_approve_administrador_ok(self):
        category = LessonCategory.objects.create(name="Cat Lecciones A4 D")
        lesson = LessonLearned.objects.create(
            title="Leccion A4 D",
            description="desc",
            category=category,
            situation="situacion",
            lesson="leccion",
            recommendations="recomendaciones",
            created_by=self.ejecutor,
            status=LessonLearned.Status.PENDING_REVIEW,
        )
        self.client.force_login(self.administrador)
        response = self.client.post(
            reverse("lessons_learned:approve", kwargs={"lesson_id": lesson.id})
        )
        # Ruta no-HTMX: éxito = redirect al detalle (nunca 403 "No autorizado").
        self.assertRedirects(
            response, reverse("lessons_learned:detail", kwargs={"lesson_id": lesson.id})
        )
        lesson.refresh_from_db()
        self.assertEqual(lesson.status, LessonLearned.Status.APPROVED)

    # --- 7. reports/views.py — @user_passes_test(_is_administrador) -----

    def test_reports_scheduled_list_administrador_ok(self):
        self.client.force_login(self.administrador)
        response = self.client.get(reverse("reports:scheduled-list"))
        self.assertEqual(response.status_code, 200)

    def test_reports_scheduled_list_ejecutor_bloqueado(self):
        self.client.force_login(self.ejecutor)
        response = self.client.get(reverse("reports:scheduled-list"))
        self.assertEqual(response.status_code, 302)

    # --- 8. gamification/views.py — require_rol (ex-staff_member_required)

    def test_gamification_admin_dashboard_administrador_ok(self):
        self.client.force_login(self.administrador)
        response = self.client.get(reverse("gamification:admin-dashboard"))
        self.assertEqual(response.status_code, 200)

    def test_gamification_admin_dashboard_ejecutor_bloqueado(self):
        self.client.force_login(self.ejecutor)
        response = self.client.get(reverse("gamification:admin-dashboard"))
        self.assertRedirects(response, reverse("gamification:dashboard"))
