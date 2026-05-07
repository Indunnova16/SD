"""
Tests for learning paths API endpoints.
"""

from datetime import date

from django.test import TestCase
from django.urls import reverse

from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.courses.models import Course, Enrollment
from apps.learning_paths.models import LearningPath, PathAssignment, PathCourse


class LearningPathAPITests(TestCase):
    """Tests for LearningPath API endpoints."""

    def setUp(self):
        # Clear existing data
        LearningPath.objects.all().delete()
        Course.objects.all().delete()

        self.client = APIClient()
        self.user = User.objects.create_user(
            email="pathtest@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
            document_number="12345678",
            job_position="Developer",
            job_profile=None,
            hire_date=date(2024, 1, 1),
        )
        self.client.force_authenticate(user=self.user)

        self.course1 = Course.objects.create(
            code="PATH-C1",
            title="Curso 1",
            description="Primer curso",
            created_by=self.user,
        )
        self.course2 = Course.objects.create(
            code="PATH-C2",
            title="Curso 2",
            description="Segundo curso",
            created_by=self.user,
        )

        self.path = LearningPath.objects.create(
            name="Ruta Liniero",
            description="Ruta de formación para linieros",
            target_profiles=["LINIERO"],
            status=LearningPath.Status.ACTIVE,
            is_mandatory=True,
            estimated_duration=30,
            created_by=self.user,
        )

        self.path_course1 = PathCourse.objects.create(
            learning_path=self.path,
            course=self.course1,
            order=1,
            is_required=True,
        )
        self.path_course2 = PathCourse.objects.create(
            learning_path=self.path,
            course=self.course2,
            order=2,
            is_required=True,
            unlock_after=self.path_course1,
        )

    def test_list_learning_paths(self):
        """Test listing learning paths."""
        url = reverse("learning_paths_api:path-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 1)

    def test_filter_paths_by_profile(self):
        """Test filtering paths by profile."""
        url = reverse("learning_paths_api:path-list")
        response = self.client.get(url, {"profile": "LINIERO"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 1)

    def test_filter_paths_mandatory(self):
        """Test filtering mandatory paths."""
        url = reverse("learning_paths_api:path-list")
        response = self.client.get(url, {"mandatory": "true"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(results), 1)

    def test_get_path_detail(self):
        """Test getting path detail."""
        url = reverse("learning_paths_api:path-detail", args=[self.path.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Ruta Liniero")
        self.assertEqual(len(response.data["path_courses"]), 2)

    def test_create_learning_path(self):
        """Test creating a new learning path."""
        url = reverse("learning_paths_api:path-list")
        data = {
            "name": "Nueva Ruta",
            "description": "Descripción de nueva ruta",
            "target_profiles": ["JEFE_CUADRILLA"],
            "is_mandatory": False,
            "estimated_duration": 15,
        }
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(LearningPath.objects.count(), 2)
        new_path = LearningPath.objects.get(name="Nueva Ruta")
        self.assertEqual(new_path.created_by, self.user)

    def test_activate_path(self):
        """Test activating a learning path."""
        draft_path = LearningPath.objects.create(
            name="Ruta Borrador",
            description="Descripción",
            target_profiles=["LINIERO"],
            status=LearningPath.Status.DRAFT,
            estimated_duration=10,
            created_by=self.user,
        )

        url = reverse("learning_paths_api:path-activate", args=[draft_path.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        draft_path.refresh_from_db()
        self.assertEqual(draft_path.status, LearningPath.Status.ACTIVE)

    def test_add_course_to_path(self):
        """Test adding a course to a path."""
        new_course = Course.objects.create(
            code="PATH-C3",
            title="Curso 3",
            description="Tercer curso",
            created_by=self.user,
        )

        url = reverse("learning_paths_api:path-add-course", args=[self.path.id])
        data = {"course": new_course.id, "order": 3, "is_required": True}
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(self.path.path_courses.count(), 3)

    def test_join_learning_path(self):
        """Test joining a learning path."""
        url = reverse("learning_paths_api:join-path", args=[self.path.id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            PathAssignment.objects.filter(
                user=self.user,
                learning_path=self.path,
            ).exists()
        )
        # Check auto-enrollment in courses
        self.assertEqual(
            Enrollment.objects.filter(user=self.user).count(),
            2,
        )


class PathAssignmentAPITests(TestCase):
    """Tests for PathAssignment API endpoints."""

    def setUp(self):
        # Clear existing data
        PathAssignment.objects.all().delete()
        LearningPath.objects.all().delete()

        self.client = APIClient()
        self.user = User.objects.create_user(
            email="assigntest@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
            document_number="22345678",
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

        self.path = LearningPath.objects.create(
            name="Ruta Test",
            description="Ruta de prueba",
            target_profiles=["LINIERO"],
            status=LearningPath.Status.ACTIVE,
            is_mandatory=True,
            estimated_duration=30,
            created_by=self.user,
        )

    def test_create_assignment(self):
        """Test creating an assignment."""
        url = reverse("learning_paths_api:assignment-list")
        data = {
            "user": self.other_user.id,
            "learning_path": self.path.id,
            "due_date": "2025-12-31",
        }
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(PathAssignment.objects.count(), 1)
        assignment = PathAssignment.objects.first()
        self.assertEqual(assignment.assigned_by, self.user)

    def test_bulk_assignment(self):
        """Test bulk assignment."""
        url = reverse("learning_paths_api:assignment-bulk-assign")
        data = {
            "user_ids": [self.user.id, self.other_user.id],
            "learning_path_id": self.path.id,
            "due_date": "2025-12-31",
        }
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["created"], 2)
        self.assertEqual(PathAssignment.objects.count(), 2)

    def test_my_learning_paths(self):
        """Test getting current user's learning paths."""
        PathAssignment.objects.create(
            user=self.user,
            learning_path=self.path,
            assigned_by=self.user,
        )

        url = reverse("learning_paths_api:my-paths")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)

    def test_filter_assignments_by_status(self):
        """Test filtering assignments by status."""
        PathAssignment.objects.create(
            user=self.user,
            learning_path=self.path,
            status=PathAssignment.Status.IN_PROGRESS,
            assigned_by=self.user,
        )

        url = reverse("learning_paths_api:my-paths")
        response = self.client.get(url, {"status": "in_progress"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
