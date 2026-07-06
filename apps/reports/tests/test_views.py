"""Tests para el gating RBAC de `apps/reports/views.py` (SD#58, sub-item A10).

Cubre:
  - Las 10 vistas de dashboard cross-usuario (`admin_dashboard` + 9 más:
    `dashboard_stats`, `compliance_chart`, `training_trend`, `expiring_certs`,
    `overdue_assignments`, `recent_activity`, `course_progress`,
    `course_type_distribution`, `assessment_performance`) exigen
    `require_rol(Rol.ADMINISTRADOR)` — gap real confirmado por F1/F2, cerrado
    acá: antes de A10 estas vistas NO tenían NINGÚN gate (solo
    `@login_required`), cualquier usuario autenticado veía métricas
    cross-usuario.
  - Los 3 `scheduled_*` (`scheduled_list`, `schedule_create`,
    `schedule_toggle`) migran de `@user_passes_test(_is_administrador)` al
    MISMO `require_rol` que el resto del gating RBAC del issue #58, por
    consistencia (ver PLAN A10).
  - Regresión: las 5 vistas personales (`report_list`, `generate_report`,
    `my_reports`, `report_status`, `delete_report`, filtradas por
    `generated_by=request.user`) NO se tocaron — siguen accesibles para
    cualquier rol autenticado, incluido `rol=None` (bucket "sin asignar" del
    backfill de A1).
"""

import itertools
from datetime import date

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.permissions import Rol
from apps.reports.models import GeneratedReport, ReportTemplate, ScheduledReport

User = get_user_model()

_SEQ = itertools.count(1)


def _make_user(rol=None, **overrides):
    """Crea un User mínimo válido para tests de apps/reports (issue #58, A10)."""
    n = next(_SEQ)
    defaults = {
        "email": f"a10_reports_user_{n}@example.com",
        "password": "testpass123",
        "first_name": f"User{n}",
        "last_name": "A10",
        "document_type": "CC",
        "document_number": f"71{n:07d}",
        "job_position": "Tech",
        "job_profile": None,
        "hire_date": date(2024, 1, 1),
        "rol": rol,
    }
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


# Las 10 vistas de dashboard cross-usuario — todas migradas al mismo
# require_rol(ADMINISTRADOR, redirect_url="reports:list").
DASHBOARD_URL_NAMES = [
    "reports:dashboard",
    "reports:dashboard-stats",
    "reports:dashboard-compliance-chart",
    "reports:dashboard-training-trend",
    "reports:dashboard-expiring-certs",
    "reports:dashboard-overdue-assignments",
    "reports:dashboard-recent-activity",
    "reports:dashboard-course-progress",
    "reports:dashboard-course-types",
    "reports:dashboard-assessment-performance",
]


class ReportsAdminDashboardGateTests(TestCase):
    """Las 10 vistas cross-usuario de reports/views.py exigen ADMINISTRADOR."""

    def setUp(self):
        self.client = Client()
        self.administrador = _make_user(rol=Rol.ADMINISTRADOR)
        self.coordinador = _make_user(rol=Rol.COORDINADOR)
        self.ejecutor = _make_user(rol=Rol.EJECUTOR)

    def test_las_10_vistas_dashboard_administrador_ok(self):
        self.client.force_login(self.administrador)
        for name in DASHBOARD_URL_NAMES:
            with self.subTest(view=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200, f"{name} falló para Administrador")

    def test_las_10_vistas_dashboard_ejecutor_bloqueado(self):
        self.client.force_login(self.ejecutor)
        for name in DASHBOARD_URL_NAMES:
            with self.subTest(view=name):
                response = self.client.get(reverse(name))
                self.assertRedirects(response, reverse("reports:list"))

    def test_las_10_vistas_dashboard_coordinador_bloqueado(self):
        """Coordinador NO es Administrador — el dashboard cross-usuario
        sigue siendo Administrador-only (A10 no amplía el acceso)."""
        self.client.force_login(self.coordinador)
        for name in DASHBOARD_URL_NAMES:
            with self.subTest(view=name):
                response = self.client.get(reverse(name))
                self.assertRedirects(response, reverse("reports:list"))

    def test_usuario_anonimo_redirige_a_login_primero(self):
        """@login_required corre ANTES que @require_rol — anónimo va a
        login, no al redirect_url del gate de rol."""
        response = self.client.get(reverse("reports:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)


class ReportsScheduledGateTests(TestCase):
    """Los 3 scheduled_* migran a require_rol (ex user_passes_test(_is_administrador))."""

    def setUp(self):
        self.client = Client()
        self.administrador = _make_user(rol=Rol.ADMINISTRADOR)
        self.ejecutor = _make_user(rol=Rol.EJECUTOR)
        self.template = ReportTemplate.objects.create(
            name="Plantilla Programada A10",
            report_type=ReportTemplate.Type.TRAINING,
            default_format=ReportTemplate.Format.PDF,
            columns=[{"name": "usuario", "type": "string"}],
            filters=[],
            is_active=True,
            created_by=self.administrador,
        )

    def test_scheduled_list_administrador_ok(self):
        self.client.force_login(self.administrador)
        response = self.client.get(reverse("reports:scheduled-list"))
        self.assertEqual(response.status_code, 200)

    def test_scheduled_list_ejecutor_bloqueado(self):
        self.client.force_login(self.ejecutor)
        response = self.client.get(reverse("reports:scheduled-list"))
        self.assertRedirects(response, reverse("reports:list"))

    def test_schedule_create_administrador_ok(self):
        self.client.force_login(self.administrador)
        response = self.client.post(
            reverse("reports:schedule-create"),
            {
                "template": self.template.id,
                "frequency": "daily",
                "time_of_day": "08:00",
                "recipients": "admin@example.com",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            ScheduledReport.objects.filter(template=self.template, created_by=self.administrador).exists()
        )

    def test_schedule_create_ejecutor_bloqueado(self):
        self.client.force_login(self.ejecutor)
        response = self.client.post(
            reverse("reports:schedule-create"),
            {
                "template": self.template.id,
                "frequency": "daily",
                "time_of_day": "08:00",
                "recipients": "a@b.com",
            },
        )
        self.assertRedirects(response, reverse("reports:list"))
        self.assertFalse(ScheduledReport.objects.filter(template=self.template).exists())

    def test_schedule_toggle_administrador_ok(self):
        schedule = ScheduledReport.objects.create(
            template=self.template,
            name="Programado A10",
            frequency=ScheduledReport.Frequency.DAILY,
            format=ReportTemplate.Format.PDF,
            time_of_day="08:00",
            created_by=self.administrador,
            recipients=["admin@example.com"],
            is_active=True,
        )
        self.client.force_login(self.administrador)
        response = self.client.post(reverse("reports:schedule-toggle", args=[schedule.id]))
        self.assertEqual(response.status_code, 200)

    def test_schedule_toggle_ejecutor_bloqueado(self):
        schedule = ScheduledReport.objects.create(
            template=self.template,
            name="Programado A10 B",
            frequency=ScheduledReport.Frequency.DAILY,
            format=ReportTemplate.Format.PDF,
            time_of_day="08:00",
            created_by=self.administrador,
            recipients=["admin@example.com"],
            is_active=True,
        )
        self.client.force_login(self.ejecutor)
        response = self.client.post(reverse("reports:schedule-toggle", args=[schedule.id]))
        self.assertRedirects(response, reverse("reports:list"))


class ReportsPersonalViewsRegressionTests(TestCase):
    """Regresión: las 5 vistas personales NO se tocaron en A10 — cualquier
    rol autenticado (incluido rol=None) sigue accediendo, porque el filtro
    real es `generated_by=request.user`, no `rol`."""

    def setUp(self):
        self.client = Client()
        self.ejecutor = _make_user(rol=Rol.EJECUTOR)
        self.coordinador = _make_user(rol=Rol.COORDINADOR)
        self.sin_rol = _make_user(rol=None)
        self.template = ReportTemplate.objects.create(
            name="Plantilla Personal A10",
            report_type=ReportTemplate.Type.TRAINING,
            default_format=ReportTemplate.Format.PDF,
            columns=[{"name": "usuario", "type": "string"}],
            filters=[],
            is_active=True,
            created_by=self.ejecutor,
        )

    def test_report_list_cualquier_rol_ok(self):
        for user in (self.ejecutor, self.coordinador, self.sin_rol):
            with self.subTest(user=user.email):
                self.client.force_login(user)
                response = self.client.get(reverse("reports:list"))
                self.assertEqual(response.status_code, 200)

    def test_my_reports_cualquier_rol_ok(self):
        for user in (self.ejecutor, self.coordinador, self.sin_rol):
            with self.subTest(user=user.email):
                self.client.force_login(user)
                response = self.client.get(reverse("reports:my-reports"))
                self.assertEqual(response.status_code, 200)

    def test_report_status_cualquier_rol_ok_si_es_dueno(self):
        for user in (self.ejecutor, self.coordinador, self.sin_rol):
            with self.subTest(user=user.email):
                report = GeneratedReport.objects.create(
                    template=self.template,
                    name=f"Reporte de {user.email}",
                    format=ReportTemplate.Format.PDF,
                    status=GeneratedReport.Status.COMPLETED,
                    generated_by=user,
                )
                self.client.force_login(user)
                response = self.client.get(reverse("reports:status", args=[report.id]))
                self.assertEqual(response.status_code, 200)

    def test_generate_report_cualquier_rol_ok(self):
        for user in (self.ejecutor, self.coordinador, self.sin_rol):
            with self.subTest(user=user.email):
                self.client.force_login(user)
                response = self.client.post(
                    reverse("reports:generate", args=[self.template.id]),
                    {"format": ReportTemplate.Format.PDF},
                )
                self.assertEqual(response.status_code, 200)

    def test_delete_report_cualquier_rol_ok_si_es_dueno(self):
        for user in (self.ejecutor, self.coordinador, self.sin_rol):
            with self.subTest(user=user.email):
                report = GeneratedReport.objects.create(
                    template=self.template,
                    name=f"Reporte a borrar de {user.email}",
                    format=ReportTemplate.Format.PDF,
                    status=GeneratedReport.Status.COMPLETED,
                    generated_by=user,
                )
                self.client.force_login(user)
                response = self.client.delete(reverse("reports:delete", args=[report.id]))
                self.assertEqual(response.status_code, 200)
                self.assertFalse(GeneratedReport.objects.filter(id=report.id).exists())
