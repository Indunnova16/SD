"""
Tests for learning paths services.
"""

from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.courses.models import Course, Enrollment
from apps.learning_paths.models import LearningPath, PathAssignment, PathCourse
from apps.learning_paths.services import LearningPathService


class LearningPathServiceTest(TestCase):
    """Tests for LearningPathService."""

    def setUp(self):
        """Set up test data."""
        self.admin = User.objects.create_user(
            email="admin@test.com",
            password="testpass123",
            first_name="Admin",
            last_name="User",
            document_number="123456789",
            job_position="Administrator",
            hire_date=date(2020, 1, 1),
            is_staff=True,
        )
        self.user = User.objects.create_user(
            email="user@test.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
            document_number="987654321",
            job_position="Technician",
            job_profile=None,
            hire_date=date(2021, 6, 15),
        )

        # Create courses
        self.course1 = Course.objects.create(
            code="COURSE-001",
            title="Course 1",
            created_by=self.admin,
            status=Course.Status.PUBLISHED,
        )
        self.course2 = Course.objects.create(
            code="COURSE-002",
            title="Course 2",
            created_by=self.admin,
            status=Course.Status.PUBLISHED,
        )
        self.course3 = Course.objects.create(
            code="COURSE-003",
            title="Course 3",
            created_by=self.admin,
            status=Course.Status.PUBLISHED,
        )

        # Create learning path
        self.path = LearningPath.objects.create(
            name="Test Path",
            description="A test learning path",
            estimated_duration=180,
            created_by=self.admin,
            status=LearningPath.Status.ACTIVE,
            target_profiles=["technician"],
        )

        # Add courses to path
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
        self.path_course3 = PathCourse.objects.create(
            learning_path=self.path,
            course=self.course3,
            order=3,
            is_required=False,
        )

    def test_assign_path_to_user(self):
        """Test assigning a learning path to a user."""
        assignment = LearningPathService.assign_path_to_user(
            user=self.user,
            learning_path=self.path,
            assigned_by=self.admin,
        )

        self.assertIsNotNone(assignment)
        self.assertEqual(assignment.user, self.user)
        self.assertEqual(assignment.learning_path, self.path)
        self.assertEqual(assignment.assigned_by, self.admin)
        self.assertEqual(assignment.status, PathAssignment.Status.ASSIGNED)

        # Check enrollments created for required courses
        enrollments = Enrollment.objects.filter(user=self.user)
        self.assertEqual(enrollments.count(), 2)  # Only required courses

    def test_assign_path_idempotent(self):
        """Test that re-assigning returns existing assignment."""
        assignment1 = LearningPathService.assign_path_to_user(
            user=self.user,
            learning_path=self.path,
            assigned_by=self.admin,
        )
        assignment2 = LearningPathService.assign_path_to_user(
            user=self.user,
            learning_path=self.path,
            assigned_by=self.admin,
        )

        self.assertEqual(assignment1.id, assignment2.id)

    def test_assign_path_with_due_date(self):
        """Test assigning with a due date."""
        due_date = timezone.now().date() + timedelta(days=30)

        assignment = LearningPathService.assign_path_to_user(
            user=self.user,
            learning_path=self.path,
            assigned_by=self.admin,
            due_date=due_date,
        )

        self.assertEqual(assignment.due_date, due_date)

    def test_reassign_completed_path(self):
        """Test re-assigning a completed path resets progress."""
        # Create and complete assignment
        assignment = LearningPathService.assign_path_to_user(
            user=self.user,
            learning_path=self.path,
            assigned_by=self.admin,
        )
        assignment.status = PathAssignment.Status.COMPLETED
        assignment.progress = 100
        assignment.completed_at = timezone.now()
        assignment.save()

        # Re-assign
        reassignment = LearningPathService.assign_path_to_user(
            user=self.user,
            learning_path=self.path,
            assigned_by=self.admin,
        )

        self.assertEqual(reassignment.id, assignment.id)
        self.assertEqual(reassignment.status, PathAssignment.Status.ASSIGNED)
        self.assertEqual(reassignment.progress, 0)
        self.assertIsNone(reassignment.completed_at)

    def test_check_path_prerequisites(self):
        """Test checking prerequisites for a path."""
        LearningPathService.assign_path_to_user(
            user=self.user,
            learning_path=self.path,
            assigned_by=self.admin,
        )

        result = LearningPathService.check_path_prerequisites(self.user, self.path)

        # Course 2 is blocked because course 1 isn't complete
        self.assertTrue(result["can_start"])
        self.assertEqual(len(result["blocked_courses"]), 1)
        self.assertEqual(result["blocked_courses"][0]["course"], "Course 2")
        self.assertEqual(result["blocked_courses"][0]["requires"], "Course 1")

    def test_check_prerequisites_all_unlocked(self):
        """Test when all prerequisites are met."""
        LearningPathService.assign_path_to_user(
            user=self.user,
            learning_path=self.path,
            assigned_by=self.admin,
        )

        # Complete course 1
        enrollment = Enrollment.objects.get(user=self.user, course=self.course1)
        enrollment.status = Enrollment.Status.COMPLETED
        enrollment.save()

        result = LearningPathService.check_path_prerequisites(self.user, self.path)

        self.assertTrue(result["can_start"])
        self.assertEqual(len(result["blocked_courses"]), 0)

    def test_update_assignment_progress(self):
        """Test updating assignment progress."""
        assignment = LearningPathService.assign_path_to_user(
            user=self.user,
            learning_path=self.path,
            assigned_by=self.admin,
        )

        # Complete first course
        enrollment = Enrollment.objects.get(user=self.user, course=self.course1)
        enrollment.status = Enrollment.Status.COMPLETED
        enrollment.save()

        updated = LearningPathService.update_assignment_progress(assignment)

        # 1 of 2 required courses = 50%
        self.assertEqual(updated.progress, 50)
        self.assertEqual(updated.status, PathAssignment.Status.IN_PROGRESS)
        self.assertIsNotNone(updated.started_at)

    def test_update_progress_complete(self):
        """Test progress updates to complete when all courses done."""
        assignment = LearningPathService.assign_path_to_user(
            user=self.user,
            learning_path=self.path,
            assigned_by=self.admin,
        )

        # Complete both required courses
        for course in [self.course1, self.course2]:
            enrollment = Enrollment.objects.get(user=self.user, course=course)
            enrollment.status = Enrollment.Status.COMPLETED
            enrollment.save()

        updated = LearningPathService.update_assignment_progress(assignment)

        self.assertEqual(updated.progress, 100)
        self.assertEqual(updated.status, PathAssignment.Status.COMPLETED)
        self.assertIsNotNone(updated.completed_at)

    def test_get_user_path_progress(self):
        """Test getting detailed progress for a user."""
        assignment = LearningPathService.assign_path_to_user(
            user=self.user,
            learning_path=self.path,
            assigned_by=self.admin,
        )

        progress = LearningPathService.get_user_path_progress(self.user, self.path)

        self.assertEqual(progress["assignment_id"], assignment.id)
        self.assertEqual(progress["path_name"], "Test Path")
        self.assertEqual(len(progress["courses"]), 3)

        # Check course 2 is locked
        course2_progress = next(c for c in progress["courses"] if c["course_id"] == self.course2.id)
        self.assertTrue(course2_progress["is_locked"])

    def test_get_user_path_progress_not_assigned(self):
        """Test getting progress when not assigned."""
        result = LearningPathService.get_user_path_progress(self.user, self.path)

        self.assertIn("error", result)

    def test_get_overdue_assignments(self):
        """Test getting overdue assignments."""
        # Create assignment with past due date
        assignment = LearningPathService.assign_path_to_user(
            user=self.user,
            learning_path=self.path,
            assigned_by=self.admin,
            due_date=timezone.now().date() - timedelta(days=1),
        )

        overdue = LearningPathService.get_overdue_assignments()

        self.assertEqual(overdue.count(), 1)
        self.assertEqual(overdue.first().id, assignment.id)

    def test_get_expiring_assignments(self):
        """Test getting assignments expiring soon."""
        # Create assignment with due date in 5 days
        assignment = LearningPathService.assign_path_to_user(
            user=self.user,
            learning_path=self.path,
            assigned_by=self.admin,
            due_date=timezone.now().date() + timedelta(days=5),
        )

        expiring = LearningPathService.get_expiring_assignments(days_ahead=7)

        self.assertEqual(expiring.count(), 1)
        self.assertEqual(expiring.first().id, assignment.id)

    def test_get_expiring_excludes_completed(self):
        """Test that completed assignments are not in expiring list."""
        assignment = LearningPathService.assign_path_to_user(
            user=self.user,
            learning_path=self.path,
            assigned_by=self.admin,
            due_date=timezone.now().date() + timedelta(days=5),
        )
        assignment.status = PathAssignment.Status.COMPLETED
        assignment.save()

        expiring = LearningPathService.get_expiring_assignments(days_ahead=7)

        self.assertEqual(expiring.count(), 0)
