"""
API views for learning paths app.
"""

from django.db.models import Q
from django.shortcuts import get_object_or_404

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.courses.models import Enrollment
from apps.learning_paths.models import LearningPath, PathAssignment, PathCourse

from .serializers import (
    BulkPathAssignmentSerializer,
    LearningPathCreateSerializer,
    LearningPathListSerializer,
    LearningPathSerializer,
    PathAssignmentCreateSerializer,
    PathAssignmentSerializer,
    PathCourseCreateSerializer,
    PathCourseSerializer,
)


class LearningPathViewSet(viewsets.ModelViewSet):
    """ViewSet for LearningPath CRUD operations."""

    queryset = LearningPath.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "list":
            return LearningPathListSerializer
        if self.action == "create":
            return LearningPathCreateSerializer
        return LearningPathSerializer

    def get_queryset(self):
        from django.conf import settings

        queryset = LearningPath.objects.prefetch_related(
            "path_courses", "path_courses__course"
        ).select_related("created_by")

        # Filter by status
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filter by profile - use icontains for SQLite compatibility
        profile = self.request.query_params.get("profile")
        if profile:
            # For PostgreSQL use __contains, for SQLite use icontains on string
            db_engine = settings.DATABASES["default"]["ENGINE"]
            if "postgresql" in db_engine:
                queryset = queryset.filter(target_profiles__contains=[profile])
            else:
                # Fallback for SQLite - filter in Python or use icontains
                queryset = queryset.filter(target_profiles__icontains=profile)

        # Filter mandatory only
        mandatory = self.request.query_params.get("mandatory")
        if mandatory and mandatory.lower() == "true":
            queryset = queryset.filter(is_mandatory=True)

        # Search by name
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(description__icontains=search))

        return queryset

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        """Activate a learning path."""
        path = self.get_object()
        if path.status == LearningPath.Status.ACTIVE:
            return Response(
                {"error": "La ruta ya está activa"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        path.status = LearningPath.Status.ACTIVE
        path.save()
        return Response({"status": "Ruta activada"})

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        """Archive a learning path."""
        path = self.get_object()
        path.status = LearningPath.Status.ARCHIVED
        path.save()
        return Response({"status": "Ruta archivada"})

    @action(detail=True, methods=["post"])
    def add_course(self, request, pk=None):
        """Add a course to the learning path."""
        path = self.get_object()
        serializer = PathCourseCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Check if course already in path
        if PathCourse.objects.filter(
            learning_path=path,
            course=serializer.validated_data["course"],
        ).exists():
            return Response(
                {"error": "El curso ya está en la ruta"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer.save(learning_path=path)
        return Response(
            PathCourseSerializer(serializer.instance, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["delete"], url_path="courses/(?P<course_id>[^/.]+)")
    def remove_course(self, request, pk=None, course_id=None):
        """Remove a course from the learning path."""
        path = self.get_object()
        path_course = get_object_or_404(PathCourse, learning_path=path, course_id=course_id)
        path_course.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def reorder_courses(self, request, pk=None):
        """Reorder courses in the learning path."""
        path = self.get_object()
        course_orders = request.data.get("course_orders", [])

        for item in course_orders:
            PathCourse.objects.filter(
                learning_path=path,
                course_id=item["course_id"],
            ).update(order=item["order"])

        return Response({"status": "Orden actualizado"})

    @action(detail=True, methods=["get"])
    def user_progress(self, request, pk=None):
        """Get detailed user progress on this learning path."""
        path = self.get_object()
        assignment = PathAssignment.objects.filter(
            user=request.user,
            learning_path=path,
        ).first()

        if not assignment:
            return Response(
                {"error": "No estás inscrito en esta ruta"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Get course completion status
        courses_progress = []
        path_courses = path.path_courses.select_related("course")
        course_ids = [pc.course.id for pc in path_courses]
        enrollments_map = {
            e.course_id: e
            for e in Enrollment.objects.filter(user=request.user, course_id__in=course_ids)
        }

        for path_course in path_courses:
            enrollment = enrollments_map.get(path_course.course.id)

            courses_progress.append(
                {
                    "course_id": path_course.course.id,
                    "course_title": path_course.course.title,
                    "order": path_course.order,
                    "is_required": path_course.is_required,
                    "enrollment_status": enrollment.status if enrollment else None,
                    "progress": float(enrollment.progress) if enrollment else 0,
                    "is_completed": enrollment and enrollment.status == Enrollment.Status.COMPLETED,
                }
            )

        return Response(
            {
                "assignment": PathAssignmentSerializer(assignment).data,
                "courses_progress": courses_progress,
            }
        )


class PathAssignmentViewSet(viewsets.ModelViewSet):
    """ViewSet for PathAssignment CRUD operations."""

    queryset = PathAssignment.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "create":
            return PathAssignmentCreateSerializer
        return PathAssignmentSerializer

    def get_queryset(self):
        queryset = PathAssignment.objects.select_related("user", "learning_path", "assigned_by")

        # Filter by user
        user_id = self.request.query_params.get("user")
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        # Filter by learning path
        path_id = self.request.query_params.get("learning_path")
        if path_id:
            queryset = queryset.filter(learning_path_id=path_id)

        # Filter by status
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset

    @action(detail=False, methods=["post"])
    def bulk_assign(self, request):
        """Assign a learning path to multiple users."""
        serializer = BulkPathAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_ids = serializer.validated_data["user_ids"]
        learning_path_id = serializer.validated_data["learning_path_id"]
        due_date = serializer.validated_data.get("due_date")

        learning_path = get_object_or_404(LearningPath, pk=learning_path_id)
        assignments = []

        for user_id in user_ids:
            assignment, created = PathAssignment.objects.get_or_create(
                user_id=user_id,
                learning_path=learning_path,
                defaults={
                    "due_date": due_date,
                    "assigned_by": request.user,
                },
            )
            if created:
                assignments.append(assignment)
                # Auto-enroll in all courses
                self._auto_enroll_courses(assignment)

        return Response(
            {
                "created": len(assignments),
                "skipped": len(user_ids) - len(assignments),
            },
            status=status.HTTP_201_CREATED,
        )

    def _auto_enroll_courses(self, assignment):
        """Auto-enroll user in all courses of the learning path."""
        path_courses = assignment.learning_path.path_courses.select_related("course")
        course_ids = [pc.course_id for pc in path_courses]

        # Get existing enrollments
        existing = set(
            Enrollment.objects.filter(user=assignment.user, course_id__in=course_ids).values_list(
                "course_id", flat=True
            )
        )

        # Create missing enrollments in bulk
        to_create = [
            Enrollment(
                user=assignment.user,
                course=path_course.course,
                assigned_by=assignment.assigned_by,
                due_date=assignment.due_date,
            )
            for path_course in path_courses
            if path_course.course_id not in existing
        ]

        if to_create:
            Enrollment.objects.bulk_create(to_create, ignore_conflicts=True)


class MyLearningPathsView(APIView):
    """View for current user's learning path assignments."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Get current user's learning path assignments."""
        assignments = PathAssignment.objects.filter(user=request.user).select_related(
            "learning_path"
        )

        status_filter = request.query_params.get("status")
        if status_filter:
            assignments = assignments.filter(status=status_filter)

        serializer = PathAssignmentSerializer(assignments, many=True)
        return Response(serializer.data)


class JoinLearningPathView(APIView):
    """View for joining a learning path."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        """Join a learning path."""
        learning_path = get_object_or_404(
            LearningPath,
            pk=pk,
            status=LearningPath.Status.ACTIVE,
        )

        assignment, created = PathAssignment.objects.get_or_create(
            user=request.user,
            learning_path=learning_path,
            defaults={"assigned_by": request.user},
        )

        if created:
            # Auto-enroll in all courses
            path_courses = learning_path.path_courses.select_related("course")
            course_ids = [pc.course_id for pc in path_courses]

            # Get existing enrollments
            existing = set(
                Enrollment.objects.filter(user=request.user, course_id__in=course_ids).values_list(
                    "course_id", flat=True
                )
            )

            # Create missing enrollments in bulk
            to_create = [
                Enrollment(
                    user=request.user,
                    course=path_course.course,
                    assigned_by=request.user,
                )
                for path_course in path_courses
                if path_course.course_id not in existing
            ]

            if to_create:
                Enrollment.objects.bulk_create(to_create, ignore_conflicts=True)

        serializer = PathAssignmentSerializer(assignment)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


# NOTE: The update_path_assignment_progress functionality has been moved to
# LearningPathService.update_assignment_progress() in apps/learning_paths/services.py
# Use: LearningPathService.update_assignment_progress(assignment)
