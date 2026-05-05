"""
Business logic services for learning paths.
"""

import logging
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.courses.models import Enrollment
from apps.learning_paths.models import LearningPath, PathAssignment

logger = logging.getLogger(__name__)


class LearningPathService:
    """Service for learning path operations."""

    @staticmethod
    @transaction.atomic
    def assign_path_to_user(
        user,
        learning_path: LearningPath,
        assigned_by=None,
        due_date=None,
    ) -> PathAssignment:
        """
        Assign a learning path to a user and create course enrollments.
        """
        # Check if already assigned
        existing = PathAssignment.objects.filter(
            user=user,
            learning_path=learning_path,
        ).first()

        if existing:
            if existing.status == PathAssignment.Status.COMPLETED:
                # Allow re-assignment for refresher
                existing.status = PathAssignment.Status.ASSIGNED
                existing.progress = 0
                existing.started_at = None
                existing.completed_at = None
                existing.due_date = due_date
                existing.assigned_by = assigned_by
                existing.save()
                return existing
            return existing

        # Create path assignment
        assignment = PathAssignment.objects.create(
            user=user,
            learning_path=learning_path,
            assigned_by=assigned_by,
            due_date=due_date,
        )

        # Create course enrollments for all courses in the path
        path_courses = learning_path.path_courses.filter(is_required=True).select_related("course")
        course_ids = [pc.course_id for pc in path_courses]

        # Get existing enrollments
        existing = set(
            Enrollment.objects.filter(user=user, course_id__in=course_ids).values_list(
                "course_id", flat=True
            )
        )

        # Create missing enrollments in bulk
        to_create = [
            Enrollment(
                user=user,
                course=path_course.course,
                assigned_by=assigned_by,
                due_date=due_date,
            )
            for path_course in path_courses
            if path_course.course_id not in existing
        ]

        if to_create:
            Enrollment.objects.bulk_create(to_create, ignore_conflicts=True)

        return assignment

    @staticmethod
    def assign_path_by_profile(job_profile: str, assigned_by=None) -> list:
        """
        Assign mandatory learning paths to all users with a specific profile.
        """
        from apps.accounts.models import User

        assignments = []

        # Find active mandatory paths for this profile
        paths = LearningPath.objects.filter(
            status=LearningPath.Status.ACTIVE,
            is_mandatory=True,
        )

        # Filter paths that include this profile
        matching_paths = [path for path in paths if job_profile in path.target_profiles]

        # Find users with this profile
        users = User.objects.filter(
            job_profile__code=job_profile,
            is_active=True,
        )

        for user in users:
            for path in matching_paths:
                try:
                    assignment = LearningPathService.assign_path_to_user(
                        user=user,
                        learning_path=path,
                        assigned_by=assigned_by,
                    )
                    assignments.append(assignment)
                except ValueError as e:
                    # Errores de validacion (ej: usuario ya asignado, prerequisitos no cumplidos)
                    logger.warning(
                        f"Error de validacion asignando ruta {path.id} a usuario {user.id}: {e}"
                    )
                except IntegrityError as e:
                    # Errores de base de datos (ej: violacion de unicidad)
                    logger.error(
                        f"Error de integridad asignando ruta {path.id} a usuario {user.id}: {e}"
                    )
                except Exception as e:
                    logger.exception(
                        f"Error inesperado asignando ruta {path.id} a usuario {user.id}: {e}"
                    )

        return assignments

    @staticmethod
    def check_path_prerequisites(user, learning_path: LearningPath) -> dict:
        """
        Check if user meets prerequisites for all courses in a path.
        """
        result = {
            "can_start": True,
            "blocked_courses": [],
            "unlocked_courses": [],
        }

        path_courses = learning_path.path_courses.select_related("course", "unlock_after__course")

        # Get all prerequisite courses in one query
        prereq_course_ids = [pc.unlock_after.course_id for pc in path_courses if pc.unlock_after]
        completed_enrollments = set(
            Enrollment.objects.filter(
                user=user,
                course_id__in=prereq_course_ids,
                status=Enrollment.Status.COMPLETED,
            ).values_list("course_id", flat=True)
        )

        for path_course in path_courses:
            # Check if course has a prerequisite in the path
            if path_course.unlock_after:
                prereq_course = path_course.unlock_after.course
                if prereq_course.id not in completed_enrollments:
                    result["blocked_courses"].append(
                        {
                            "course": path_course.course.title,
                            "requires": prereq_course.title,
                        }
                    )
                else:
                    result["unlocked_courses"].append(path_course.course.title)
            else:
                result["unlocked_courses"].append(path_course.course.title)

        result["can_start"] = (
            len(result["blocked_courses"]) == 0 or len(result["unlocked_courses"]) > 0
        )
        return result

    @staticmethod
    def update_assignment_progress(assignment: PathAssignment) -> PathAssignment:
        """
        Update path assignment progress based on course completions.
        """
        total_required = assignment.learning_path.path_courses.filter(is_required=True).count()

        if total_required == 0:
            return assignment

        # Count completed courses
        path_courses = assignment.learning_path.path_courses.filter(is_required=True)
        course_ids = list(path_courses.values_list("course_id", flat=True))

        completed = Enrollment.objects.filter(
            user=assignment.user,
            course_id__in=course_ids,
            status=Enrollment.Status.COMPLETED,
        ).count()

        # Calculate progress
        progress = (completed / total_required) * 100
        assignment.progress = round(progress, 2)

        # Update status
        if progress > 0 and assignment.status == PathAssignment.Status.ASSIGNED:
            assignment.status = PathAssignment.Status.IN_PROGRESS
            assignment.started_at = timezone.now()

        if progress >= 100:
            assignment.status = PathAssignment.Status.COMPLETED
            assignment.completed_at = timezone.now()

        # Check for overdue
        if assignment.due_date and assignment.due_date < timezone.now().date():
            if assignment.status != PathAssignment.Status.COMPLETED:
                assignment.status = PathAssignment.Status.OVERDUE

        assignment.save()
        return assignment

    @staticmethod
    def get_user_path_progress(user, learning_path: LearningPath) -> dict:
        """
        Get detailed progress for a user in a learning path.
        """
        assignment = PathAssignment.objects.filter(
            user=user,
            learning_path=learning_path,
        ).first()

        if not assignment:
            return {"error": "User is not assigned to this path"}

        courses_progress = []
        for path_course in learning_path.path_courses.all():
            enrollment = Enrollment.objects.filter(
                user=user,
                course=path_course.course,
            ).first()

            # Check if locked
            is_locked = False
            locked_reason = None
            if path_course.unlock_after:
                prereq_enrollment = Enrollment.objects.filter(
                    user=user,
                    course=path_course.unlock_after.course,
                    status=Enrollment.Status.COMPLETED,
                ).first()
                if not prereq_enrollment:
                    is_locked = True
                    locked_reason = f"Requiere completar: {path_course.unlock_after.course.title}"

            courses_progress.append(
                {
                    "course_id": path_course.course.id,
                    "course_title": path_course.course.title,
                    "order": path_course.order,
                    "is_required": path_course.is_required,
                    "is_locked": is_locked,
                    "locked_reason": locked_reason,
                    "status": enrollment.status if enrollment else "not_enrolled",
                    "progress": float(enrollment.progress) if enrollment else 0,
                }
            )

        return {
            "assignment_id": assignment.id,
            "path_name": learning_path.name,
            "overall_progress": float(assignment.progress),
            "status": assignment.status,
            "due_date": assignment.due_date.isoformat() if assignment.due_date else None,
            "started_at": assignment.started_at.isoformat() if assignment.started_at else None,
            "completed_at": assignment.completed_at.isoformat()
            if assignment.completed_at
            else None,
            "courses": courses_progress,
        }

    @staticmethod
    def get_overdue_assignments():
        """Get all overdue path assignments."""
        today = timezone.now().date()
        return PathAssignment.objects.filter(
            due_date__lt=today,
            status__in=[
                PathAssignment.Status.ASSIGNED,
                PathAssignment.Status.IN_PROGRESS,
            ],
        ).select_related("user", "learning_path")

    @staticmethod
    def get_expiring_assignments(days_ahead: int = 7):
        """Get assignments expiring within the specified days."""
        today = timezone.now().date()
        deadline = today + timedelta(days=days_ahead)

        return PathAssignment.objects.filter(
            due_date__gte=today,
            due_date__lte=deadline,
            status__in=[
                PathAssignment.Status.ASSIGNED,
                PathAssignment.Status.IN_PROGRESS,
            ],
        ).select_related("user", "learning_path")
