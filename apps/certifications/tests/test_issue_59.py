"""
Tests for SD#59 — Certificado de curso: 3 sub-items del Sprint A.

  A1: certificate_template.html:175 used `{{ course.duration_hours|default:
      "N/A" }}` — Django's `default` filter treats 0/0.0 as falsy, so a
      legitimately-computed `duration_hours=0.0` (SD#43) rendered "N/A"
      instead of "0.0". Fixed with an explicit `is not None` check.
      Reproduces the real prod bug: course id=79 "INDUCCIÓN SEGURIDAD VIAL"
      has duration_hours=0.0 and an already-issued certificate (id=28)
      showing "N/A horas".

  A2: `certificate_templates` has 0 rows in prod -> CertificateService.
      issue_certificate() never finds an `is_active=True` template, so
      every certificate falls back to the "SD" text logo. Fixed by (1)
      making `CertificateTemplate.template_file` optional (migration 0003)
      and (2) seeding one active template with the client's real logo
      (migration 0004, RunPython idempotent).

  A3: the signature block used `template.signer_name`/`signature_image`
      (global fields of a single template), never who actually assigned
      the course to the recipient. `_resolve_certificate_signer()` now
      resolves `Enrollment.assigned_by`, with a fallback to
      `course.created_by` when `assigned_by` is null OR is the SAME person
      as the certificate recipient (self-enrollment via
      enroll_course/learning_paths sets `assigned_by=request.user`).
"""

from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import render_to_string
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.certifications.forms import CertificateTemplateForm
from apps.certifications.models import Certificate, CertificateTemplate
from apps.certifications.services import CertificateService
from apps.courses.models import Course, Enrollment, Lesson, Module

# Minimal valid 1x1 transparent PNG, same fixture pattern as
# apps/courses/tests/test_attendance_pdf.py, so ImageField validation passes.
_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000154a24f000000004945454e44ae42"
    "6082"
)

_SEQ = [2000]


def _png_file(name="logo.png"):
    return SimpleUploadedFile(name, _PNG_BYTES, content_type="image/png")


def _make_user(**overrides):
    _SEQ[0] += 1
    n = _SEQ[0]
    defaults = {
        "email": f"issue59_user_{n}@test.com",
        "password": "testpass123",
        "first_name": f"User{n}",
        "last_name": "Issue59",
        "document_number": f"59{n:07d}",
        "job_position": "Coordinador HSEQ",
        "hire_date": date(2022, 1, 1),
    }
    defaults.update(overrides)
    return User.objects.create_user(**defaults)


def _make_course(creator, **overrides):
    _SEQ[0] += 1
    n = _SEQ[0]
    defaults = {
        "code": f"ISSUE59-{n}",
        "title": f"Curso Issue 59 #{n}",
        "description": "desc",
        "status": Course.Status.PUBLISHED,
        "validity_months": 12,
        "created_by": creator,
    }
    defaults.update(overrides)
    return Course.objects.create(**defaults)


class CertificateDurationHoursDisplayTest(TestCase):
    """A1: certificate_template.html renders `course.duration_hours` even
    when the value is exactly 0.0, instead of falling back to 'N/A'."""

    def setUp(self):
        self.admin = _make_user(job_position="Administrator")
        self.recipient = _make_user()

    def _render(self, course):
        context = {
            "certificate": None,
            "user": self.recipient,
            "course": course,
            "template": None,
            "issued_date": timezone.now(),
            "expires_date": None,
            "verification_url": "https://lms.sd.com.co/certifications/verify/TEST/",
            "certificate_number": "SD-TEST-00000000",
        }
        return render_to_string("certifications/certificate_template.html", context)

    def test_happy_path_positive_duration_renders_value(self):
        """Happy path: a normal positive duration (0.3h, 18 min of lesson —
        mirrors the real prod course id=63) renders '0.3 horas'."""
        course = _make_course(self.admin, code="ISSUE59-A1-POS")
        module = Module.objects.create(course=course, title="M1", description="d", order=0)
        Lesson.objects.create(
            module=module,
            title="L1",
            lesson_type=Lesson.Type.VIDEO,
            duration=18,
            order=0,
        )
        self.assertEqual(course.duration_hours, 0.3)

        html = self._render(course)
        # es-co locale renders the decimal separator as ',' (Django L10N) —
        # this already matched pre-fix behavior for non-zero values.
        self.assertIn("0,3 horas", html)
        self.assertNotIn("N/A horas", html)

    def test_edge_zero_duration_from_lessons_renders_zero_not_na(self):
        """Edge case (the actual bug): lessons summing to 0 minutes give
        duration_hours=0.0 — must render '0.0 horas', not 'N/A horas'.
        Mirrors the real prod course id=79 'INDUCCIÓN SEGURIDAD VIAL'
        (already-issued certificate id=28 showing the bug)."""
        course = _make_course(self.admin, code="ISSUE59-A1-ZERO")
        module = Module.objects.create(course=course, title="M1", description="d", order=0)
        Lesson.objects.create(
            module=module,
            title="L1 (sin duración)",
            lesson_type=Lesson.Type.TEXT,
            duration=0,
            order=0,
        )
        self.assertEqual(course.duration_hours, 0.0)

        html = self._render(course)
        self.assertIn("0,0 horas", html)
        self.assertNotIn("N/A horas", html)

    def test_edge_no_modules_at_all_renders_zero_not_na(self):
        """Edge case: a course with NO modules (aggregate returns no rows at
        all, a different DB path than 'modules with 0-duration lessons')
        also renders '0.0 horas', not 'N/A horas'."""
        course = _make_course(self.admin, code="ISSUE59-A1-NOMOD")
        self.assertEqual(course.duration_hours, 0.0)

        html = self._render(course)
        self.assertIn("0,0 horas", html)
        self.assertNotIn("N/A horas", html)


class CertificateTemplateFileOptionalTest(TestCase):
    """A2 (part 1): CertificateTemplate.template_file is now optional —
    an admin can create a "logo/firma only" template with no custom
    .html/.pdf file attached."""

    def test_happy_path_form_valid_without_template_file(self):
        form = CertificateTemplateForm(
            data={
                "name": "Plantilla sin archivo",
                "description": "",
                "signer_name": "",
                "signer_title": "",
                "is_active": True,
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        template = form.save()
        self.assertFalse(template.template_file)

    def test_edge_model_saves_directly_without_template_file(self):
        """Edge case: creating the model directly (not via the form) with no
        template_file must pass full_clean() now that blank=True."""
        template = CertificateTemplate(name="Solo logo", is_active=True)
        template.full_clean()  # must not raise ValidationError
        template.save()
        self.assertFalse(template.template_file)

    def test_edge_form_still_valid_with_template_file_attached(self):
        """Regression: templates that DO attach a custom template_file still
        validate and save correctly (optional != broken when present)."""
        html_file = SimpleUploadedFile(
            "custom.html", b"<html><body>{{ user }}</body></html>", content_type="text/html"
        )
        form = CertificateTemplateForm(
            data={
                "name": "Plantilla con archivo",
                "description": "",
                "signer_name": "Director",
                "signer_title": "S.D. S.A.S.",
                "is_active": True,
            },
            files={"template_file": html_file},
        )
        self.assertTrue(form.is_valid(), form.errors)
        template = form.save()
        self.assertTrue(template.template_file)


class CertificateGenerationUsesActiveTemplateLogoTest(TestCase):
    """A2 (part 2): a newly-issued certificate inherits the active seeded
    template (so its logo renders instead of the 'SD' text fallback)."""

    def setUp(self):
        # Migration 0004 (A2) seeds one active default CertificateTemplate in
        # every env, including this test DB — neutralize it so each test
        # controls its own is_active state deterministically.
        CertificateTemplate.objects.update(is_active=False)

        self.admin = _make_user(job_position="Administrator")
        self.user = _make_user()
        self.course = _make_course(self.admin, code="ISSUE59-A2-GEN")
        self.enrollment = Enrollment.objects.create(
            user=self.user,
            course=self.course,
            status=Enrollment.Status.COMPLETED,
            progress=100,
        )

    def _mock_generate(self, certificate):
        certificate.status = Certificate.Status.ISSUED
        certificate.issued_at = timezone.now()
        certificate.save()
        return certificate

    def test_happy_path_new_certificate_inherits_active_template(self):
        """When exactly one active template exists (the A2-seeded default),
        `issue_certificate` attaches it to the new certificate."""
        template = CertificateTemplate.objects.create(name="Activa", is_active=True)
        template.logo.save("logo.png", _png_file(), save=True)

        import unittest.mock as mock

        with mock.patch.object(
            CertificateService, "generate_certificate_file", side_effect=self._mock_generate
        ):
            certificate = CertificateService.issue_certificate(self.user, self.course)

        self.assertEqual(certificate.template_id, template.id)

    def test_edge_no_active_template_falls_back_to_none(self):
        """Edge case: with zero active templates (pre-A2 prod state), the
        certificate's `template` stays None — same fallback behavior as
        before, no crash."""
        import unittest.mock as mock

        with mock.patch.object(
            CertificateService, "generate_certificate_file", side_effect=self._mock_generate
        ):
            certificate = CertificateService.issue_certificate(self.user, self.course)

        self.assertIsNone(certificate.template_id)

    def test_edge_template_with_blank_file_still_renders_default_html_with_logo(self):
        """Edge case: the seeded template has template_file blank (A2's
        migration leaves it empty on purpose) — `_generate_pdf`'s context
        still resolves `template` to a real (non-None) instance, so
        certificate_template.html's `{% if template and template.logo %}`
        renders the real logo `<img>` instead of the 'SD' text fallback."""
        template = CertificateTemplate.objects.create(name="Activa (sin archivo)", is_active=True)
        template.logo.save("logo.png", _png_file(), save=True)
        self.assertFalse(template.template_file)

        html = render_to_string(
            "certifications/certificate_template.html",
            {
                "certificate": None,
                "user": self.user,
                "course": self.course,
                "template": template,
                "issued_date": timezone.now(),
                "expires_date": None,
                "verification_url": "https://lms.sd.com.co/certifications/verify/TEST/",
                "certificate_number": "SD-TEST-00000001",
            },
        )
        self.assertIn(template.logo.url, html)
        self.assertNotIn('<div class="logo-fallback">SD</div>', html)
