"""
Tests for courses API endpoints.
"""

from datetime import date

from django.test import TestCase, override_settings
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Contract, User
from apps.courses.models import Category, Course, Enrollment, Lesson, Module


@override_settings(
    REST_FRAMEWORK={
        "DEFAULT_AUTHENTICATION_CLASSES": [
            "rest_framework_simplejwt.authentication.JWTAuthentication",
            "rest_framework.authentication.SessionAuthentication",
        ],
        "DEFAULT_PERMISSION_CLASSES": [
            "rest_framework.permissions.IsAuthenticated",
        ],
    }
)
class CategoryAPITests(TestCase):
    """Tests for Category API endpoints."""

    def setUp(self):
        # Clear existing data
        Category.objects.all().delete()

        self.client = APIClient()
        self.user = User.objects.create_user(
            email="cattest@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
            document_number="12345678",
            job_position="Developer",
            job_profile=None,
            hire_date=date(2024, 1, 1),
        )
        self.client.force_authenticate(user=self.user)

        self.category = Category.objects.create(
            name="Seguridad",
            slug="seguridad",
            description="Cursos de seguridad",
            color="#FF0000",
        )
        self.subcategory = Category.objects.create(
            name="Trabajo en Altura",
            slug="trabajo-altura",
            description="Cursos de trabajo en altura",
            parent=self.category,
        )

    def test_list_categories(self):
        """Test listing categories."""
        url = reverse("courses_api:category-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # API may return paginated or non-paginated results
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 2)

    def test_list_root_categories_only(self):
        """Test listing only root categories."""
        url = reverse("courses_api:category-list")
        response = self.client.get(url, {"root_only": "true"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "Seguridad")

    def test_get_category_detail(self):
        """Test getting category detail."""
        url = reverse("courses_api:category-detail", args=[self.category.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Seguridad")
        self.assertEqual(len(response.data["children"]), 1)

    def test_create_category(self):
        """Test creating a new category."""
        url = reverse("courses_api:category-list")
        data = {
            "name": "Nueva Categoría",
            "slug": "nueva-categoria",
            "description": "Descripción de prueba",
            "color": "#00FF00",
        }
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Category.objects.count(), 3)

    def test_get_category_courses(self):
        """Test getting courses for a category."""
        Course.objects.create(
            code="SEC-001",
            title="Curso de Seguridad",
            description="Descripción del curso",
            category=self.category,
            status=Course.Status.PUBLISHED,
            created_by=self.user,
        )

        url = reverse("courses_api:category-courses", args=[self.category.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["title"], "Curso de Seguridad")


class CourseAPITests(TestCase):
    """Tests for Course API endpoints."""

    def setUp(self):
        # Clear existing data
        Course.objects.all().delete()
        Category.objects.all().delete()
        Contract.objects.all().delete()

        self.client = APIClient()
        self.user = User.objects.create_user(
            email="coursetest@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
            document_number="22345678",
            job_position="Developer",
            job_profile=None,
            hire_date=date(2024, 1, 1),
        )
        self.client.force_authenticate(user=self.user)

        self.category = Category.objects.create(
            name="Seguridad",
            slug="seguridad",
        )

        self.contract = Contract.objects.create(
            code="ISA-001",
            name="Contrato ISA",
            client="ISA Intercolombia",
            start_date=date(2024, 1, 1),
        )

        self.course = Course.objects.create(
            code="SEC-001",
            title="Curso de Seguridad",
            description="Descripción del curso",
            course_type=Course.Type.MANDATORY,
            category=self.category,
            status=Course.Status.PUBLISHED,
            created_by=self.user,
        )
        self.course.contracts.add(self.contract)

    def test_list_courses(self):
        """Test listing courses."""
        url = reverse("courses_api:course-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 1)

    def test_filter_courses_by_category(self):
        """Test filtering courses by category."""
        url = reverse("courses_api:course-list")
        response = self.client.get(url, {"category": self.category.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 1)

    def test_filter_courses_by_category_slug(self):
        """Test filtering courses by category slug."""
        url = reverse("courses_api:course-list")
        response = self.client.get(url, {"category_slug": "seguridad"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 1)

    def test_filter_courses_by_contract(self):
        """Test filtering courses by contract."""
        url = reverse("courses_api:course-list")
        response = self.client.get(url, {"contract": self.contract.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 1)

    def test_filter_courses_by_status(self):
        """Test filtering courses by status."""
        url = reverse("courses_api:course-list")
        response = self.client.get(url, {"status": "published"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 1)

    def test_search_courses(self):
        """Test searching courses."""
        url = reverse("courses_api:course-list")
        response = self.client.get(url, {"search": "Seguridad"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 1)

    def test_get_course_detail(self):
        """Test getting course detail."""
        url = reverse("courses_api:course-detail", args=[self.course.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "Curso de Seguridad")
        self.assertEqual(response.data["category_name"], "Seguridad")
        self.assertIn("Contrato ISA", response.data["contract_names"])

    def test_create_course(self):
        """Test creating a new course."""
        url = reverse("courses_api:course-list")
        data = {
            "code": "SEC-002",
            "title": "Nuevo Curso",
            "description": "Descripción del nuevo curso",
            "course_type": "mandatory",
            "category": self.category.id,
            "contracts": [self.contract.id],
        }
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Course.objects.count(), 2)
        new_course = Course.objects.get(code="SEC-002")
        self.assertEqual(new_course.created_by, self.user)
        self.assertIn(self.contract, new_course.contracts.all())

    def test_publish_course(self):
        """Test publishing a course."""
        draft_course = Course.objects.create(
            code="SEC-003",
            title="Curso Borrador",
            description="Descripción",
            status=Course.Status.DRAFT,
            created_by=self.user,
        )

        url = reverse("courses_api:course-publish", args=[draft_course.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        draft_course.refresh_from_db()
        self.assertEqual(draft_course.status, Course.Status.PUBLISHED)
        self.assertIsNotNone(draft_course.published_at)

    def test_archive_course(self):
        """Test archiving a course."""
        url = reverse("courses_api:course-archive", args=[self.course.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.course.refresh_from_db()
        self.assertEqual(self.course.status, Course.Status.ARCHIVED)

    def test_duplicate_course(self):
        """Test duplicating a course."""
        # Add module and lesson to the course
        module = Module.objects.create(
            course=self.course,
            title="Módulo 1",
            order=1,
        )
        Lesson.objects.create(
            module=module,
            title="Lección 1",
            lesson_type=Lesson.Type.VIDEO,
            order=1,
        )

        url = reverse("courses_api:course-duplicate", args=[self.course.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Course.objects.count(), 2)

        new_course = Course.objects.get(code=f"{self.course.code}_copy")
        self.assertEqual(new_course.status, Course.Status.DRAFT)
        self.assertEqual(new_course.modules.count(), 1)
        self.assertEqual(new_course.modules.first().lessons.count(), 1)


class ModuleAPITests(TestCase):
    """Tests for Module API endpoints."""

    def setUp(self):
        # Clear existing data
        Module.objects.all().delete()
        Course.objects.all().delete()

        self.client = APIClient()
        self.user = User.objects.create_user(
            email="modtest@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
            document_number="32345678",
            job_position="Developer",
            job_profile=None,
            hire_date=date(2024, 1, 1),
        )
        self.client.force_authenticate(user=self.user)

        self.course = Course.objects.create(
            code="MOD-001",
            title="Curso de Seguridad",
            description="Descripción del curso",
            created_by=self.user,
        )

        self.module = Module.objects.create(
            course=self.course,
            title="Módulo 1",
            description="Primer módulo",
            order=1,
        )

    def test_list_modules(self):
        """Test listing modules for a course."""
        url = reverse(
            "courses_api:course-module-list",
            kwargs={"course_pk": self.course.id},
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 1)

    def test_create_module(self):
        """Test creating a new module."""
        url = reverse(
            "courses_api:course-module-list",
            kwargs={"course_pk": self.course.id},
        )
        data = {
            "title": "Módulo 2",
            "description": "Segundo módulo",
            "order": 2,
        }
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Module.objects.count(), 2)


class EnrollmentAPITests(TestCase):
    """Tests for Enrollment API endpoints."""

    def setUp(self):
        # Clear existing data
        Enrollment.objects.all().delete()
        Course.objects.all().delete()

        self.client = APIClient()
        self.user = User.objects.create_user(
            email="enrtest@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
            document_number="42345678",
            job_position="Developer",
            job_profile=None,
            hire_date=date(2024, 1, 1),
        )
        self.other_user = User.objects.create_user(
            email="other@example.com",
            password="testpass123",
            first_name="Other",
            last_name="User",
            document_number="87654321",
            job_position="Developer",
            job_profile=None,
            hire_date=date(2024, 1, 1),
        )
        self.client.force_authenticate(user=self.user)

        self.course = Course.objects.create(
            code="ENR-001",
            title="Curso de Seguridad",
            description="Descripción del curso",
            status=Course.Status.PUBLISHED,
            created_by=self.user,
        )

    def test_create_enrollment(self):
        """Test creating an enrollment."""
        url = reverse("courses_api:enrollment-list")
        data = {
            "user": self.other_user.id,
            "course": self.course.id,
            "due_date": "2025-12-31",
        }
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Enrollment.objects.count(), 1)
        enrollment = Enrollment.objects.first()
        self.assertEqual(enrollment.assigned_by, self.user)

    def test_bulk_enrollment(self):
        """Test bulk enrollment of users."""
        url = reverse("courses_api:enrollment-bulk-enroll")
        data = {
            "user_ids": [self.user.id, self.other_user.id],
            "course_id": self.course.id,
            "due_date": "2025-12-31",
        }
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["created"], 2)
        self.assertEqual(Enrollment.objects.count(), 2)

    def test_my_enrollments(self):
        """Test getting current user's enrollments."""
        Enrollment.objects.create(
            user=self.user,
            course=self.course,
            assigned_by=self.user,
        )

        url = reverse("courses_api:my-enrollments")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_filter_enrollments_by_status(self):
        """Test filtering enrollments by status."""
        Enrollment.objects.create(
            user=self.user,
            course=self.course,
            status=Enrollment.Status.IN_PROGRESS,
            assigned_by=self.user,
        )

        url = reverse("courses_api:my-enrollments")
        response = self.client.get(url, {"status": "in_progress"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)


# =============================================================================
