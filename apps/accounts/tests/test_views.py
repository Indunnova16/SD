"""
Tests for accounts views.
"""

import base64
from datetime import date

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

User = get_user_model()

# Minimal valid 2x2 PNG that passes PIL's full verify() (Django's form-level
# ImageField.clean() calls Image.open(...).verify(), stricter than the
# model-level FileField.save() used elsewhere in the codebase — this fixture
# must survive that check, unlike a hand-truncated placeholder).
_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000002000000020802000000fdd49a73"
    "0000001649444154789c63fccfc0c0c0c0c0c4c0c0c0c0c000000d1d01036ac29be"
    "90000000049454e44ae426082"
)


def _png_file(name="signature.png"):
    return SimpleUploadedFile(name, _PNG_BYTES, content_type="image/png")


class LoginViewTests(TestCase):
    """Tests for login view."""

    def setUp(self):
        self.client = Client()
        self.login_url = reverse("accounts:login")
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpassword123",
            first_name="Test",
            last_name="User",
            document_type="CC",
            document_number="12345678",
            hire_date=date(2024, 1, 1),
        )

    def test_login_page_loads(self):
        """Test that login page loads correctly."""
        response = self.client.get(self.login_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/login.html")

    def test_login_with_valid_credentials(self):
        """Test login with valid credentials redirects to dashboard."""
        response = self.client.post(
            self.login_url,
            {"username": "12345678", "password": "testpassword123"},
        )
        self.assertEqual(response.status_code, 302)

    def test_login_with_invalid_credentials(self):
        """Test login with invalid credentials shows error."""
        response = self.client.post(
            self.login_url,
            {"username": "12345678", "password": "wrongpassword"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Credenciales inválidas")

    def test_authenticated_user_redirected(self):
        """Test authenticated user is redirected from login page."""
        self.client.login(username="12345678", password="testpassword123")
        response = self.client.get(self.login_url)
        self.assertRedirects(response, reverse("accounts:dashboard"))


class DashboardViewTests(TestCase):
    """Tests for dashboard view."""

    def setUp(self):
        self.client = Client()
        self.dashboard_url = reverse("accounts:dashboard")
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpassword123",
            first_name="Test",
            last_name="User",
            document_type="CC",
            document_number="12345678",
            hire_date=date(2024, 1, 1),
        )

    def test_dashboard_requires_login(self):
        """Test dashboard requires authentication."""
        response = self.client.get(self.dashboard_url)
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={self.dashboard_url}")

    def test_dashboard_accessible_when_logged_in(self):
        """Test dashboard is accessible when logged in."""
        self.client.login(username="12345678", password="testpassword123")
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 200)


class ProfileViewTests(TestCase):
    """Tests for profile views."""

    def setUp(self):
        self.client = Client()
        self.profile_url = reverse("accounts:profile")
        self.profile_edit_url = reverse("accounts:profile_edit")
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpassword123",
            first_name="Test",
            last_name="User",
            document_type="CC",
            document_number="12345678",
            hire_date=date(2024, 1, 1),
        )
        self.client.login(username="12345678", password="testpassword123")

    def test_profile_page_loads(self):
        """Test profile page loads correctly."""
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test User")

    def test_profile_edit_page_loads(self):
        """Test profile edit page loads correctly."""
        response = self.client.get(self.profile_edit_url)
        self.assertEqual(response.status_code, 200)

    def test_profile_update(self):
        """Test profile can be updated."""
        response = self.client.post(
            self.profile_edit_url,
            {
                "first_name": "Updated",
                "last_name": "Name",
                "phone": "3001234567",
            },
        )
        self.assertRedirects(response, self.profile_url)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Updated")
        self.assertEqual(self.user.last_name, "Name")


class PasswordResetViewTests(TestCase):
    """Tests for password reset views."""

    def setUp(self):
        self.client = Client()
        self.password_reset_url = reverse("accounts:password_reset")
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpassword123",
            first_name="Test",
            last_name="User",
            document_type="CC",
            document_number="12345678",
            hire_date=date(2024, 1, 1),
        )

    def test_password_reset_page_loads(self):
        """Test password reset page loads correctly."""
        response = self.client.get(self.password_reset_url)
        self.assertEqual(response.status_code, 200)

    def test_password_reset_request_sent(self):
        """Test password reset request is processed."""
        response = self.client.post(
            self.password_reset_url,
            {"email": "test@example.com"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Revise su correo")


class LogoutViewTests(TestCase):
    """Tests for logout view."""

    def setUp(self):
        self.client = Client()
        self.logout_url = reverse("accounts:logout")
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpassword123",
            first_name="Test",
            last_name="User",
            document_type="CC",
            document_number="12345678",
            hire_date=date(2024, 1, 1),
        )

    def test_logout_confirmation_page(self):
        """Test logout confirmation page loads."""
        self.client.login(username="12345678", password="testpassword123")
        response = self.client.get(self.logout_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "¿Desea cerrar sesión?")

    def test_logout_post(self):
        """Test logout via POST."""
        self.client.login(username="12345678", password="testpassword123")
        response = self.client.post(self.logout_url)
        self.assertRedirects(response, reverse("accounts:login"))


class ReassignEnrollmentViewTests(TestCase):
    """Tests for the staff-driven course reassignment endpoint (SD#42)."""

    def setUp(self):
        from apps.courses.models import Course, Enrollment

        self.client = Client()

        # Staff admin who performs the reassignment.
        self.admin = User.objects.create_user(
            email="admin@example.com",
            password="adminpass123",
            first_name="Admin",
            last_name="User",
            document_type="CC",
            document_number="99999999",
            hire_date=date(2024, 1, 1),
            is_staff=True,
        )
        # Regular (non-staff) user.
        self.worker = User.objects.create_user(
            email="worker@example.com",
            password="workerpass123",
            first_name="Worker",
            last_name="User",
            document_type="CC",
            document_number="11111111",
            hire_date=date(2024, 1, 1),
        )
        # Target user whose enrollment will be reassigned.
        self.learner = User.objects.create_user(
            email="learner@example.com",
            password="learnerpass123",
            first_name="Learner",
            last_name="User",
            document_type="CC",
            document_number="22222222",
            hire_date=date(2024, 1, 1),
        )

        self.course = Course.objects.create(
            code="SD42-COURSE",
            title="Curso de Prueba SD42",
            description="Curso para validar la reasignación.",
            created_by=self.admin,
            status=Course.Status.PUBLISHED,
        )
        # Completed enrollment with prior progress (representative legacy-like row).
        self.enrollment = Enrollment.objects.create(
            user=self.learner,
            course=self.course,
            status=Enrollment.Status.COMPLETED,
            progress=75,
            started_at=timezone.now(),
            completed_at=timezone.now(),
        )
        self.url = reverse(
            "accounts:reassign_enrollment",
            kwargs={"user_id": self.learner.pk, "enrollment_id": self.enrollment.pk},
        )

    def test_reassign_requires_staff(self):
        """Non-staff users are redirected and the enrollment is untouched."""
        self.client.login(username="11111111", password="workerpass123")
        response = self.client.post(self.url)
        self.assertRedirects(response, reverse("accounts:dashboard"))
        self.enrollment.refresh_from_db()
        # Status unchanged.
        self.assertEqual(self.enrollment.status, "completed")
        self.assertEqual(self.enrollment.progress, 75)

    def test_reassign_get_not_allowed(self):
        """GET is rejected by require_POST."""
        self.client.login(username="99999999", password="adminpass123")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_reassign_resets_enrollment(self):
        """Staff POST resets the enrollment back to ENROLLED with cleared dates."""
        from apps.courses.models import Enrollment

        self.client.login(username="99999999", password="adminpass123")
        response = self.client.post(self.url)
        self.assertRedirects(
            response,
            reverse(
                "accounts:user_learning_history",
                kwargs={"user_id": self.learner.pk},
            ),
        )
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, Enrollment.Status.ENROLLED)
        self.assertEqual(self.enrollment.progress, 0)
        self.assertIsNone(self.enrollment.started_at)
        self.assertIsNone(self.enrollment.completed_at)
        self.assertEqual(self.enrollment.assigned_by, self.admin)

    def test_reassign_success_message_contains_reasignado(self):
        """Success message must contain the substring asserted by the E2E journey."""
        self.client.login(username="99999999", password="adminpass123")
        response = self.client.post(self.url, follow=True)
        self.assertContains(response, "reasignado")

    def test_reassign_creates_completion_record_when_progress(self):
        """A CompletionRecord is kept for audit when there was prior progress."""
        from apps.courses.models import CompletionRecord

        self.client.login(username="99999999", password="adminpass123")
        self.client.post(self.url)
        records = CompletionRecord.objects.filter(user=self.learner, course=self.course)
        self.assertEqual(records.count(), 1)
        record = records.first()
        self.assertEqual(record.progress, 75)
        self.assertEqual(record.reset_reason, "Reasignación por administrador")
        self.assertIsNotNone(record.completed_at)

    def test_reassign_no_record_when_zero_progress(self):
        """No CompletionRecord is created when there was no progress."""
        from apps.courses.models import CompletionRecord, Enrollment

        # Fresh enrollment with zero progress.
        zero_enrollment = Enrollment.objects.create(
            user=self.learner,
            course=Course_create_helper(self),
            status=Enrollment.Status.ENROLLED,
            progress=0,
        )
        url = reverse(
            "accounts:reassign_enrollment",
            kwargs={"user_id": self.learner.pk, "enrollment_id": zero_enrollment.pk},
        )
        self.client.login(username="99999999", password="adminpass123")
        self.client.post(url)
        self.assertEqual(
            CompletionRecord.objects.filter(
                user=self.learner, course=zero_enrollment.course
            ).count(),
            0,
        )

    def test_reassign_resets_lesson_progress(self):
        """LessonProgress rows tied to the enrollment are reset (legacy data path)."""
        from apps.courses.models import Lesson, LessonProgress, Module

        module = Module.objects.create(course=self.course, title="Modulo 1", order=1)
        lesson = Lesson.objects.create(
            module=module,
            title="Leccion 1",
            lesson_type=Lesson.Type.TEXT,
            order=1,
        )
        lp = LessonProgress.objects.create(
            enrollment=self.enrollment,
            lesson=lesson,
            is_completed=True,
            progress_percent=100,
            time_spent=600,
            completed_at=timezone.now(),
        )
        self.client.login(username="99999999", password="adminpass123")
        self.client.post(self.url)
        lp.refresh_from_db()
        self.assertFalse(lp.is_completed)
        self.assertEqual(lp.progress_percent, 0)
        self.assertEqual(lp.time_spent, 0)
        self.assertIsNone(lp.completed_at)


def Course_create_helper(test_case):
    """Create a second published course for tests needing a distinct course."""
    from apps.courses.models import Course

    return Course.objects.create(
        code="SD42-COURSE-2",
        title="Curso de Prueba SD42 #2",
        description="Segundo curso para validar reasignación sin progreso.",
        created_by=test_case.admin,
        status=Course.Status.PUBLISHED,
    )


class UserEditSignatureTests(TestCase):
    """Tests for `signature` en /accounts/users/<id>/edit/ (SD#51, A2).

    Covers: subida de archivo (input[name=signature]) persiste, firma
    dibujada en canvas (signature_canvas_data base64) persiste, y guardar
    el form sin tocar la firma NO borra una firma existente (edge case
    explícitamente pedido por el plan).
    """

    def setUp(self):
        self.client = Client()
        self.admin = User.objects.create_user(
            email="admin_sig@example.com",
            password="adminpass123",
            first_name="Admin",
            last_name="Sig",
            document_type="CC",
            document_number="990000001",
            hire_date=date(2024, 1, 1),
            is_staff=True,
            job_position="Coordinador HSEQ",
        )
        self.target = User.objects.create_user(
            email="target_sig@example.com",
            password="targetpass123",
            first_name="Target",
            last_name="Sig",
            document_type="CC",
            document_number="990000002",
            hire_date=date(2024, 1, 1),
            job_position="Liniero",
        )
        self.url = reverse("accounts:user_edit", kwargs={"user_id": self.target.pk})
        self.client.login(username="990000001", password="adminpass123")

    def _base_post_data(self, **overrides):
        data = {
            "email": self.target.email,
            "first_name": self.target.first_name,
            "last_name": self.target.last_name,
            "document_type": self.target.document_type,
            "document_number": self.target.document_number,
            "phone": "",
            "job_position": self.target.job_position,
            "employment_type": "direct",
            "hire_date": "2024-01-01",
            "status": "active",
        }
        data.update(overrides)
        return data

    def test_upload_file_persists_signature(self):
        """Subir un archivo por input[name=signature] persiste en users.signature."""
        data = self._base_post_data()
        response = self.client.post(self.url, data={**data, "signature": _png_file()})
        self.assertEqual(response.status_code, 302)

        self.target.refresh_from_db()
        self.assertTrue(self.target.signature)
        self.assertIn("users/signatures/", self.target.signature.name)

    def test_canvas_base64_persists_signature(self):
        """Firma dibujada en canvas (signature_canvas_data base64) persiste."""
        b64 = base64.b64encode(_PNG_BYTES).decode("ascii")
        data_url = f"data:image/png;base64,{b64}"

        data = self._base_post_data(signature_canvas_data=data_url)
        response = self.client.post(self.url, data=data)
        self.assertEqual(response.status_code, 302)

        self.target.refresh_from_db()
        self.assertTrue(self.target.signature)
        self.assertIn("users/signatures/", self.target.signature.name)

    def test_saving_without_touching_signature_does_not_wipe_existing(self):
        """Edge case obligatorio del plan: guardar otros campos SIN tocar la
        firma no debe borrar una firma existente.

        Cambia `phone` (no `job_position`): un cambio de cargo dispara la
        creación de un JobHistory que, en este repo, ya falla hoy con
        job_profile=None (previous_profile NOT NULL) — bug preexistente
        ajeno a SD#51/A2, no forma parte de este scope.
        """
        self.target.signature.save("existing.png", _png_file(), save=True)
        self.target.refresh_from_db()
        self.assertTrue(self.target.signature)
        existing_name = self.target.signature.name

        data = self._base_post_data(phone="+57 300 999 8888")
        response = self.client.post(self.url, data=data)
        self.assertEqual(response.status_code, 302)

        self.target.refresh_from_db()
        self.assertTrue(self.target.signature)
        self.assertEqual(self.target.signature.name, existing_name)
        self.assertEqual(self.target.phone, "+57 300 999 8888")

    def test_invalid_canvas_data_does_not_break_save(self):
        """Edge case: signature_canvas_data mal formado no rompe el guardado
        (se ignora, el resto del form se guarda igual)."""
        data = self._base_post_data(
            phone="+57 300 999 8888", signature_canvas_data="not-a-valid-data-url"
        )
        response = self.client.post(self.url, data=data)
        self.assertEqual(response.status_code, 302)

        self.target.refresh_from_db()
        self.assertFalse(self.target.signature)
        self.assertEqual(self.target.phone, "+57 300 999 8888")
