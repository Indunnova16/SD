"""
Tests for course builder web views (HTMX endpoints).
"""

from datetime import date

from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.assessments.models import Assessment
from apps.courses.models import Category, Course


class BuilderEditAssessmentViewTests(TestCase):
    """Tests for builder_edit_assessment view (issue SD#38)."""

    def setUp(self):
        self.client = Client()

        self.staff = User.objects.create_user(
            email="staff_edit@test.com",
            password="testpass123",
            first_name="Staff",
            last_name="User",
            document_number="20000001",
            job_position="Admin",
            job_profile=None,
            hire_date=date(2024, 1, 1),
            is_staff=True,
        )
        self.creator = User.objects.create_user(
            email="creator_edit@test.com",
            password="testpass123",
            first_name="Creator",
            last_name="User",
            document_number="20000002",
            job_position="Instructor",
            job_profile=None,
            hire_date=date(2024, 1, 1),
        )
        self.other = User.objects.create_user(
            email="other_edit@test.com",
            password="testpass123",
            first_name="Other",
            last_name="User",
            document_number="20000003",
            job_position="Tech",
            job_profile=None,
            hire_date=date(2024, 1, 1),
        )

        self.category = Category.objects.create(
            name="Seguridad SD38",
            slug="seguridad-sd38",
            description="cat",
            color="#FF0000",
        )
        self.course = Course.objects.create(
            code="COURSE-SD38-1",
            title="Curso SD38",
            description="desc",
            objectives="obj",
            course_type=Course.Type.MANDATORY,
            status=Course.Status.DRAFT,
            category=self.category,
            created_by=self.staff,
        )
        self.assessment = Assessment.objects.create(
            title="Quiz inicial",
            description="desc original",
            assessment_type="quiz",
            passing_score=70,
            time_limit=30,
            max_attempts=3,
            shuffle_questions=True,
            shuffle_answers=True,
            show_correct_answers=True,
            status="draft",
            course=self.course,
            created_by=self.creator,
        )

        self.url = reverse(
            "courses:builder_edit_assessment",
            kwargs={"course_id": self.course.id, "assessment_id": self.assessment.id},
        )

    def test_get_renders_form_for_staff(self):
        self.client.force_login(self.staff)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Editar propiedades")
        self.assertContains(resp, "Quiz inicial")

    def test_get_renders_form_for_creator(self):
        self.client.force_login(self.creator)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Editar propiedades")

    def test_get_forbidden_for_other_user_htmx(self):
        self.client.force_login(self.other)
        resp = self.client.get(self.url, HTTP_HX_REQUEST="true")
        self.assertEqual(resp.status_code, 403)

    def test_post_valid_updates_assessment(self):
        self.client.force_login(self.staff)
        resp = self.client.post(
            self.url,
            data={
                "title": "Quiz actualizado",
                "description": "nueva desc",
                "assessment_type": "exam",
                "passing_score": 85,
                "time_limit": 45,
                "max_attempts": 5,
                "shuffle_questions": "on",
                "shuffle_answers": "on",
                "show_correct_answers": "on",
                "status": "published",
            },
        )
        self.assertEqual(resp.status_code, 200)
        # HX-Trigger header set
        self.assertEqual(resp.headers.get("HX-Trigger"), "assessment-updated")

        self.assessment.refresh_from_db()
        self.assertEqual(self.assessment.title, "Quiz actualizado")
        self.assertEqual(self.assessment.description, "nueva desc")
        self.assertEqual(self.assessment.assessment_type, "exam")
        self.assertEqual(self.assessment.passing_score, 85)
        self.assertEqual(self.assessment.time_limit, 45)
        self.assertEqual(self.assessment.max_attempts, 5)
        self.assertEqual(self.assessment.status, "published")

    def test_post_invalid_passing_score_returns_400(self):
        self.client.force_login(self.staff)
        resp = self.client.post(
            self.url,
            data={
                "title": "Quiz",
                "description": "",
                "assessment_type": "quiz",
                "passing_score": 150,  # invalid
                "time_limit": "",
                "max_attempts": 3,
                "status": "draft",
            },
        )
        self.assertEqual(resp.status_code, 400)
        # assessment unchanged
        self.assessment.refresh_from_db()
        self.assertEqual(self.assessment.passing_score, 70)

    def test_post_forbidden_for_other_user(self):
        self.client.force_login(self.other)
        resp = self.client.post(
            self.url,
            data={
                "title": "Hack",
                "assessment_type": "quiz",
                "passing_score": 50,
                "max_attempts": 1,
                "status": "draft",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 403)
        self.assessment.refresh_from_db()
        self.assertEqual(self.assessment.title, "Quiz inicial")

    def test_anonymous_redirected(self):
        resp = self.client.get(self.url)
        # @login_required redirects to login
        self.assertIn(resp.status_code, (302, 301))

    def test_post_does_not_change_created_by(self):
        """Regression: created_by must NEVER be editable via this form."""
        self.client.force_login(self.staff)
        original_creator_id = self.assessment.created_by_id
        self.client.post(
            self.url,
            data={
                "title": "Quiz",
                "description": "",
                "assessment_type": "quiz",
                "passing_score": 80,
                "time_limit": "",
                "max_attempts": 3,
                "status": "draft",
                "created_by": self.staff.id,  # attempt to overwrite
            },
        )
        self.assessment.refresh_from_db()
        self.assertEqual(self.assessment.created_by_id, original_creator_id)
