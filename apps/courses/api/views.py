"""
API views for courses app.
"""

from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.courses.models import (
    Category,
    Course,
    CourseVersion,
    Enrollment,
    Lesson,
    LessonProgress,
    MediaAsset,
    Module,
    ResourceLibrary,
    ScormAttempt,
    ScormPackage,
)
from apps.courses.services import EnrollmentService

from .serializers import (
    BulkEnrollmentSerializer,
    CategoryListSerializer,
    CategorySerializer,
    CourseCreateSerializer,
    CourseListSerializer,
    CourseSerializer,
    CourseVersionCreateSerializer,
    CourseVersionSerializer,
    EnrollmentCreateSerializer,
    EnrollmentSerializer,
    LessonProgressSerializer,
    LessonProgressUpdateSerializer,
    LessonSerializer,
    MediaAssetSerializer,
    ModuleSerializer,
    ResourceLibraryCreateSerializer,
    ResourceLibraryListSerializer,
    ResourceLibrarySerializer,
    ScormAttemptSerializer,
    ScormDataUpdateSerializer,
    ScormPackageSerializer,
)


class CategoryViewSet(viewsets.ModelViewSet):
    """ViewSet for Category CRUD operations."""

    queryset = Category.objects.filter(is_active=True)
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "list":
            return CategoryListSerializer
        return CategorySerializer

    def get_queryset(self):
        queryset = Category.objects.filter(is_active=True)

        return queryset.annotate(
            course_count=Count("courses", filter=Q(courses__status="published"))
        ).order_by("order", "name")

    @action(detail=True, methods=["get"])
    def courses(self, request, pk=None):
        """Get all courses in this category."""
        category = self.get_object()
        courses = Course.objects.filter(category=category, status=Course.Status.PUBLISHED)
        serializer = CourseListSerializer(courses, many=True)
        return Response(serializer.data)


class CourseViewSet(viewsets.ModelViewSet):
    """ViewSet for Course CRUD operations."""

    queryset = Course.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "list":
            return CourseListSerializer
        if self.action == "create":
            return CourseCreateSerializer
        return CourseSerializer

    def get_queryset(self):
        queryset = Course.objects.prefetch_related(
            "modules", "modules__lessons", "category", "contracts"
        ).select_related("category", "created_by")

        # Filter by status
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filter by course type
        course_type = self.request.query_params.get("type")
        if course_type:
            queryset = queryset.filter(course_type=course_type)

        # Filter by target profile
        profile = self.request.query_params.get("profile")
        if profile:
            queryset = queryset.filter(target_profiles__contains=[profile])

        # Filter by category
        category = self.request.query_params.get("category")
        if category:
            queryset = queryset.filter(category_id=category)

        # Filter by category slug
        category_slug = self.request.query_params.get("category_slug")
        if category_slug:
            queryset = queryset.filter(category__slug=category_slug)

        # Filter by contract
        contract = self.request.query_params.get("contract")
        if contract:
            queryset = queryset.filter(contracts__id=contract)

        # Search by title or code
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(Q(title__icontains=search) | Q(code__icontains=search))

        return queryset.distinct()

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        """Publish a course."""
        course = self.get_object()
        if course.status == Course.Status.PUBLISHED:
            return Response(
                {"error": "Course is already published"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        course.status = Course.Status.PUBLISHED
        course.published_at = timezone.now()
        course.save()

        return Response({"status": "Course published"})

    @action(detail=True, methods=["post"])
    def archive(self, request, pk=None):
        """Archive a course."""
        course = self.get_object()
        course.status = Course.Status.ARCHIVED
        course.save()
        return Response({"status": "Course archived"})

    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        """Duplicate a course with all modules and lessons."""
        original = self.get_object()

        with transaction.atomic():
            # Clone course
            new_course = Course.objects.create(
                code=f"{original.code}_copy",
                title=f"{original.title} (copia)",
                description=original.description,
                objectives=original.objectives,
                course_type=original.course_type,
                target_profiles=original.target_profiles,
                validity_months=original.validity_months,
                created_by=request.user,
                status=Course.Status.DRAFT,
            )

            # Clone modules and lessons
            for module in original.modules.all():
                new_module = Module.objects.create(
                    course=new_course,
                    title=module.title,
                    description=module.description,
                    order=module.order,
                )

                for lesson in module.lessons.all():
                    Lesson.objects.create(
                        module=new_module,
                        title=lesson.title,
                        description=lesson.description,
                        lesson_type=lesson.lesson_type,
                        content=lesson.content,
                        video_url=lesson.video_url,
                        duration=lesson.duration,
                        order=lesson.order,
                        is_mandatory=lesson.is_mandatory,
                        is_offline_available=lesson.is_offline_available,
                        metadata=lesson.metadata,
                    )

        serializer = CourseSerializer(new_course)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ModuleViewSet(viewsets.ModelViewSet):
    """ViewSet for Module CRUD operations."""

    serializer_class = ModuleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        course_id = self.kwargs.get("course_pk")
        return Module.objects.filter(course_id=course_id).prefetch_related("lessons")

    def perform_create(self, serializer):
        course_id = self.kwargs.get("course_pk")
        course = get_object_or_404(Course, pk=course_id)
        serializer.save(course=course)


class LessonViewSet(viewsets.ModelViewSet):
    """ViewSet for Lesson CRUD operations."""

    serializer_class = LessonSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        module_id = self.kwargs.get("module_pk")
        return Lesson.objects.filter(module_id=module_id)

    def perform_create(self, serializer):
        module_id = self.kwargs.get("module_pk")
        module = get_object_or_404(Module, pk=module_id)
        serializer.save(module=module)


class MediaAssetViewSet(viewsets.ModelViewSet):
    """ViewSet for MediaAsset CRUD operations."""

    queryset = MediaAsset.objects.all()
    serializer_class = MediaAssetSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = MediaAsset.objects.all()

        file_type = self.request.query_params.get("type")
        if file_type:
            queryset = queryset.filter(file_type=file_type)

        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset

    def perform_create(self, serializer):
        serializer.save(uploaded_by=self.request.user)


class EnrollmentViewSet(viewsets.ModelViewSet):
    """ViewSet for Enrollment CRUD operations."""

    queryset = Enrollment.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "create":
            return EnrollmentCreateSerializer
        return EnrollmentSerializer

    def get_queryset(self):
        queryset = Enrollment.objects.select_related("user", "course", "assigned_by")

        # Filter by user
        user_id = self.request.query_params.get("user")
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        # Filter by course
        course_id = self.request.query_params.get("course")
        if course_id:
            queryset = queryset.filter(course_id=course_id)

        # Filter by status
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset

    @action(detail=False, methods=["post"])
    def bulk_enroll(self, request):
        """Enroll multiple users in a course."""
        serializer = BulkEnrollmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_ids = serializer.validated_data["user_ids"]
        course_id = serializer.validated_data["course_id"]
        due_date = serializer.validated_data.get("due_date")

        course = get_object_or_404(Course, pk=course_id)
        enrollments = []

        for user_id in user_ids:
            enrollment, created = Enrollment.objects.get_or_create(
                user_id=user_id,
                course=course,
                defaults={
                    "due_date": due_date,
                    "assigned_by": request.user,
                },
            )
            if created:
                enrollments.append(enrollment)

        return Response(
            {
                "created": len(enrollments),
                "skipped": len(user_ids) - len(enrollments),
            },
            status=status.HTTP_201_CREATED,
        )


class MyEnrollmentsView(APIView):
    """View for current user's enrollments."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Get current user's enrollments."""
        enrollments = Enrollment.objects.filter(user=request.user).select_related("course")

        status_filter = request.query_params.get("status")
        if status_filter:
            enrollments = enrollments.filter(status=status_filter)

        serializer = EnrollmentSerializer(enrollments, many=True)
        return Response(serializer.data)


class LessonProgressView(APIView):
    """View for tracking lesson progress."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, enrollment_id):
        """Get lesson progress for an enrollment."""
        enrollment = get_object_or_404(Enrollment, pk=enrollment_id, user=request.user)
        progress = LessonProgress.objects.filter(enrollment=enrollment).select_related("lesson")
        serializer = LessonProgressSerializer(progress, many=True)
        return Response(serializer.data)

    def post(self, request, enrollment_id, lesson_id):
        """Update or create lesson progress."""
        enrollment = get_object_or_404(Enrollment, pk=enrollment_id, user=request.user)
        lesson = get_object_or_404(Lesson, pk=lesson_id)

        progress, created = LessonProgress.objects.get_or_create(
            enrollment=enrollment,
            lesson=lesson,
        )

        serializer = LessonProgressUpdateSerializer(progress, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        # Mark as completed if progress is 100%
        if progress.progress_percent >= 100 and not progress.is_completed:
            progress.is_completed = True
            progress.completed_at = timezone.now()
            progress.save()

        # Update enrollment status and progress using the service
        EnrollmentService.update_enrollment_progress(enrollment)

        return Response(LessonProgressSerializer(progress).data)


class CourseVersionViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing course versions."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CourseVersionSerializer

    def get_queryset(self):
        course_id = self.kwargs.get("course_pk")
        return CourseVersion.objects.filter(course_id=course_id).select_related("created_by")


class CreateCourseVersionView(APIView):
    """View for creating a new course version."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, course_id):
        """Create a new version snapshot of a course."""
        course = get_object_or_404(Course, pk=course_id)

        serializer = CourseVersionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        version = CourseVersion.create_snapshot(
            course=course,
            user=request.user,
            changelog=serializer.validated_data.get("changelog", ""),
            is_major=serializer.validated_data.get("is_major", False),
        )

        return Response(
            CourseVersionSerializer(version).data,
            status=status.HTTP_201_CREATED,
        )


class ScormPackageViewSet(viewsets.ModelViewSet):
    """ViewSet for SCORM package management."""

    queryset = ScormPackage.objects.all()
    serializer_class = ScormPackageSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = ScormPackage.objects.select_related("lesson", "lesson__module")

        lesson_id = self.request.query_params.get("lesson")
        if lesson_id:
            queryset = queryset.filter(lesson_id=lesson_id)

        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return queryset

    def perform_create(self, serializer):
        instance = serializer.save()
        # Queue for processing
        from apps.courses.services import ScormService

        ScormService.process_package(instance)

    @action(detail=True, methods=["post"])
    def reprocess(self, request, pk=None):
        """Reprocess a SCORM package."""
        scorm_package = self.get_object()

        from apps.courses.services import ScormService

        ScormService.process_package(scorm_package)

        return Response(ScormPackageSerializer(scorm_package).data)


class ScormAttemptViewSet(viewsets.ModelViewSet):
    """ViewSet for SCORM attempts."""

    queryset = ScormAttempt.objects.all()
    serializer_class = ScormAttemptSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = ScormAttempt.objects.select_related(
            "enrollment", "enrollment__user", "scorm_package", "scorm_package__lesson"
        )

        enrollment_id = self.request.query_params.get("enrollment")
        if enrollment_id:
            queryset = queryset.filter(enrollment_id=enrollment_id)

        package_id = self.request.query_params.get("package")
        if package_id:
            queryset = queryset.filter(scorm_package_id=package_id)

        return queryset

    @action(detail=True, methods=["post"])
    def update_cmi(self, request, pk=None):
        """Update SCORM CMI data."""
        attempt = self.get_object()

        serializer = ScormDataUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        cmi_element = serializer.validated_data["cmi_element"]
        value = serializer.validated_data["value"]

        # Update CMI data
        attempt.cmi_data[cmi_element] = value

        # Handle common SCORM elements
        if cmi_element == "cmi.core.lesson_status":
            status_map = {
                "passed": ScormAttempt.Status.PASSED,
                "completed": ScormAttempt.Status.COMPLETED,
                "failed": ScormAttempt.Status.FAILED,
                "incomplete": ScormAttempt.Status.INCOMPLETE,
            }
            attempt.lesson_status = status_map.get(value, attempt.lesson_status)

        elif cmi_element == "cmi.core.score.raw":
            try:
                attempt.score_raw = float(value)
            except ValueError:
                pass

        elif cmi_element == "cmi.core.lesson_location":
            attempt.location = value

        elif cmi_element == "cmi.suspend_data":
            attempt.suspend_data = value

        attempt.save()

        return Response({"success": True, "element": cmi_element, "value": value})


class ResourceLibraryViewSet(viewsets.ModelViewSet):
    """ViewSet for resource library management."""

    queryset = ResourceLibrary.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "list":
            return ResourceLibraryListSerializer
        if self.action == "create":
            return ResourceLibraryCreateSerializer
        return ResourceLibrarySerializer

    def get_queryset(self):
        queryset = ResourceLibrary.objects.filter(is_public=True)

        resource_type = self.request.query_params.get("type")
        if resource_type:
            queryset = queryset.filter(resource_type=resource_type)

        category = self.request.query_params.get("category")
        if category:
            queryset = queryset.filter(category_id=category)

        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(description__icontains=search))

        return queryset.order_by("-usage_count", "-created_at")

    def perform_create(self, serializer):
        file = self.request.FILES.get("file")
        if file:
            serializer.save(
                uploaded_by=self.request.user,
                file_size=file.size,
            )
        else:
            serializer.save(uploaded_by=self.request.user)

    @action(detail=True, methods=["post"])
    def increment_usage(self, request, pk=None):
        """Increment usage count when resource is used."""
        resource = self.get_object()
        resource.usage_count += 1
        resource.save()
        return Response({"usage_count": resource.usage_count})

    @action(detail=False, methods=["get"])
    def popular(self, request):
        """Get most popular resources."""
        resources = ResourceLibrary.objects.filter(is_public=True).order_by("-usage_count")[:20]
        serializer = ResourceLibraryListSerializer(resources, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def my_resources(self, request):
        """Get resources uploaded by current user."""
        resources = ResourceLibrary.objects.filter(uploaded_by=request.user).order_by("-created_at")
        serializer = ResourceLibraryListSerializer(resources, many=True)
        return Response(serializer.data)
