"""
Factory classes for courses tests.

Uses factory_boy to create test data for all course-related models.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone

import factory
from factory.django import DjangoModelFactory

from apps.accounts.models import Contract
from apps.courses.models import (
    Category,
    Course,
    CourseVersion,
    Enrollment,
    JobProfileType,
    Lesson,
    LessonProgress,
    MediaAsset,
    Module,
    ResourceLibrary,
    ScormAttempt,
    ScormPackage,
)

User = get_user_model()


class JobProfileTypeFactory(DjangoModelFactory):
    """Factory for JobProfileType model (FK target of User.job_profile).

    Uses ``django_get_or_create`` on ``code`` so it reuses the rows already
    seeded by the ``0008_seed_job_profile_types`` data migration instead of
    creating duplicates when the test DB already has migrations applied.
    """

    class Meta:
        model = JobProfileType
        django_get_or_create = ("code",)

    code = "LINIERO"
    name = "Liniero"
    description = "Personal operativo - Liniero"
    is_active = True
    order = 1


class UserFactory(DjangoModelFactory):
    """Factory for User model."""

    class Meta:
        model = User
        django_get_or_create = ("email",)

    email = factory.Sequence(lambda n: f"user{n}@test.com")
    password = factory.PostGenerationMethodCall("set_password", "testpass123")
    first_name = factory.Faker("first_name", locale="es_ES")
    last_name = factory.Faker("last_name", locale="es_ES")
    document_type = "CC"
    document_number = factory.Sequence(lambda n: f"{10000000 + n}")
    job_position = "Technician"
    job_profile = factory.SubFactory(JobProfileTypeFactory)
    hire_date = factory.LazyFunction(lambda: date.today() - timedelta(days=365))
    is_active = True


class AdminUserFactory(UserFactory):
    """Factory for admin users."""

    email = factory.Sequence(lambda n: f"admin{n}@test.com")
    is_staff = True
    is_superuser = True


class SupervisorUserFactory(UserFactory):
    """Factory for supervisor users."""

    email = factory.Sequence(lambda n: f"supervisor{n}@test.com")
    job_profile = factory.SubFactory(
        JobProfileTypeFactory, code="JEFE_CUADRILLA", name="Jefe de Cuadrilla"
    )


class ContractFactory(DjangoModelFactory):
    """Factory for Contract model."""

    class Meta:
        model = Contract
        django_get_or_create = ("code",)

    code = factory.Sequence(lambda n: f"CONTRACT-{n:04d}")
    name = factory.Sequence(lambda n: f"Contrato de Prueba {n}")
    client = "ISA Intercolombia"
    description = factory.Faker("paragraph", locale="es_ES")
    start_date = factory.LazyFunction(lambda: date.today() - timedelta(days=180))
    end_date = factory.LazyFunction(lambda: date.today() + timedelta(days=180))
    is_active = True


class CategoryFactory(DjangoModelFactory):
    """Factory for Category model."""

    class Meta:
        model = Category
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Category {n}")
    slug = factory.Sequence(lambda n: f"category-{n}")
    description = factory.Faker("paragraph", locale="es_ES")
    icon = "heroicon-folder"
    color = factory.Faker("hex_color")
    order = factory.Sequence(lambda n: n)
    is_active = True


class CourseFactory(DjangoModelFactory):
    """Factory for Course model."""

    class Meta:
        model = Course
        django_get_or_create = ("code",)

    code = factory.Sequence(lambda n: f"COURSE-{n:04d}")
    title = factory.Sequence(lambda n: f"Curso de Prueba {n}")
    description = factory.Faker("paragraph", nb_sentences=5, locale="es_ES")
    objectives = factory.Faker("paragraph", nb_sentences=3, locale="es_ES")
    course_type = Course.Type.MANDATORY
    status = Course.Status.DRAFT
    version = 1
    target_profiles = factory.LazyFunction(lambda: ["LINIERO", "JEFE_CUADRILLA"])
    validity_months = 12
    category = factory.SubFactory(CategoryFactory)
    created_by = factory.SubFactory(UserFactory)


class PublishedCourseFactory(CourseFactory):
    """Factory for published courses."""

    status = Course.Status.PUBLISHED
    published_at = factory.LazyFunction(timezone.now)


class ArchivedCourseFactory(CourseFactory):
    """Factory for archived courses."""

    status = Course.Status.ARCHIVED


class MandatoryCourseFactory(CourseFactory):
    """Factory for mandatory courses."""

    course_type = Course.Type.MANDATORY


class OptionalCourseFactory(CourseFactory):
    """Factory for optional courses."""

    course_type = Course.Type.OPTIONAL


class RefresherCourseFactory(CourseFactory):
    """Factory for refresher courses."""

    course_type = Course.Type.REFRESHER


class ModuleFactory(DjangoModelFactory):
    """Factory for Module model."""

    class Meta:
        model = Module

    course = factory.SubFactory(CourseFactory)
    title = factory.Sequence(lambda n: f"Module {n}")
    description = factory.Faker("paragraph", locale="es_ES")
    order = factory.Sequence(lambda n: n)


class LessonFactory(DjangoModelFactory):
    """Factory for Lesson model."""

    class Meta:
        model = Lesson

    module = factory.SubFactory(ModuleFactory)
    title = factory.Sequence(lambda n: f"Lesson {n}")
    description = factory.Faker("paragraph", locale="es_ES")
    lesson_type = Lesson.Type.VIDEO
    content = factory.Faker("paragraph", nb_sentences=10, locale="es_ES")
    video_url = ""
    duration = factory.Faker("random_int", min=5, max=60)
    order = factory.Sequence(lambda n: n)
    is_mandatory = True
    is_offline_available = True
    metadata = factory.LazyFunction(dict)


class VideoLessonFactory(LessonFactory):
    """Factory for video lessons."""

    lesson_type = Lesson.Type.VIDEO
    video_url = factory.Faker("url")
    duration = factory.Faker("random_int", min=10, max=30)


class PDFLessonFactory(LessonFactory):
    """Factory for PDF lessons."""

    lesson_type = Lesson.Type.PDF
    duration = factory.Faker("random_int", min=5, max=15)


class ScormLessonFactory(LessonFactory):
    """Factory for SCORM lessons."""

    lesson_type = Lesson.Type.SCORM
    duration = factory.Faker("random_int", min=20, max=60)


class QuizLessonFactory(LessonFactory):
    """Factory for quiz lessons."""

    lesson_type = Lesson.Type.QUIZ
    duration = factory.Faker("random_int", min=10, max=20)
    metadata = factory.LazyFunction(
        lambda: {
            "passing_score": 3.5,
            "max_attempts": 3,
            "time_limit": 30,
        }
    )


class TextLessonFactory(LessonFactory):
    """Factory for text lessons."""

    lesson_type = Lesson.Type.TEXT
    content = factory.Faker("text", max_nb_chars=2000, locale="es_ES")
    duration = factory.Faker("random_int", min=5, max=15)


class InteractiveLessonFactory(LessonFactory):
    """Factory for interactive lessons."""

    lesson_type = Lesson.Type.INTERACTIVE
    duration = factory.Faker("random_int", min=15, max=45)


class EnrollmentFactory(DjangoModelFactory):
    """Factory for Enrollment model."""

    class Meta:
        model = Enrollment
        django_get_or_create = ("user", "course")

    user = factory.SubFactory(UserFactory)
    course = factory.SubFactory(PublishedCourseFactory)
    status = Enrollment.Status.ENROLLED
    progress = Decimal("0.00")
    started_at = None
    completed_at = None
    due_date = factory.LazyFunction(lambda: date.today() + timedelta(days=30))
    assigned_by = factory.SubFactory(UserFactory)


class InProgressEnrollmentFactory(EnrollmentFactory):
    """Factory for in-progress enrollments."""

    status = Enrollment.Status.IN_PROGRESS
    progress = factory.Faker("pydecimal", min_value=10, max_value=90, right_digits=2)
    started_at = factory.LazyFunction(lambda: timezone.now() - timedelta(days=7))


class CompletedEnrollmentFactory(EnrollmentFactory):
    """Factory for completed enrollments."""

    status = Enrollment.Status.COMPLETED
    progress = Decimal("100.00")
    started_at = factory.LazyFunction(lambda: timezone.now() - timedelta(days=14))
    completed_at = factory.LazyFunction(lambda: timezone.now() - timedelta(days=1))


class ExpiredEnrollmentFactory(EnrollmentFactory):
    """Factory for expired enrollments."""

    status = Enrollment.Status.EXPIRED
    progress = factory.Faker("pydecimal", min_value=0, max_value=90, right_digits=2)
    due_date = factory.LazyFunction(lambda: date.today() - timedelta(days=30))


class DroppedEnrollmentFactory(EnrollmentFactory):
    """Factory for dropped enrollments."""

    status = Enrollment.Status.DROPPED
    progress = factory.Faker("pydecimal", min_value=0, max_value=50, right_digits=2)


class LessonProgressFactory(DjangoModelFactory):
    """Factory for LessonProgress model."""

    class Meta:
        model = LessonProgress
        django_get_or_create = ("enrollment", "lesson")

    enrollment = factory.SubFactory(EnrollmentFactory)
    lesson = factory.SubFactory(LessonFactory)
    is_completed = False
    progress_percent = Decimal("0.00")
    time_spent = 0
    last_position = factory.LazyFunction(dict)
    completed_at = None


class CompletedLessonProgressFactory(LessonProgressFactory):
    """Factory for completed lesson progress."""

    is_completed = True
    progress_percent = Decimal("100.00")
    time_spent = factory.Faker("random_int", min=300, max=3600)
    completed_at = factory.LazyFunction(timezone.now)


class MediaAssetFactory(DjangoModelFactory):
    """Factory for MediaAsset model."""

    class Meta:
        model = MediaAsset

    filename = factory.LazyAttribute(lambda obj: f"{obj.original_name.replace(' ', '_')}")
    original_name = factory.Sequence(lambda n: f"asset_{n}.mp4")
    file = factory.django.FileField(filename="test_video.mp4")
    file_type = MediaAsset.Type.VIDEO
    mime_type = "video/mp4"
    size = factory.Faker("random_int", min=1024000, max=10240000)
    status = MediaAsset.Status.PENDING
    processing_error = ""
    duration = None
    metadata = factory.LazyFunction(dict)
    uploaded_by = factory.SubFactory(UserFactory)


class VideoAssetFactory(MediaAssetFactory):
    """Factory for video assets."""

    original_name = factory.Sequence(lambda n: f"video_{n}.mp4")
    file_type = MediaAsset.Type.VIDEO
    mime_type = "video/mp4"
    duration = factory.Faker("random_int", min=60, max=3600)


class AudioAssetFactory(MediaAssetFactory):
    """Factory for audio assets."""

    original_name = factory.Sequence(lambda n: f"audio_{n}.mp3")
    file_type = MediaAsset.Type.AUDIO
    mime_type = "audio/mpeg"
    duration = factory.Faker("random_int", min=60, max=1800)


class ImageAssetFactory(MediaAssetFactory):
    """Factory for image assets."""

    original_name = factory.Sequence(lambda n: f"image_{n}.jpg")
    file = factory.django.FileField(filename="test_image.jpg")
    file_type = MediaAsset.Type.IMAGE
    mime_type = "image/jpeg"
    duration = None


class DocumentAssetFactory(MediaAssetFactory):
    """Factory for document assets."""

    original_name = factory.Sequence(lambda n: f"document_{n}.pdf")
    file = factory.django.FileField(filename="test_document.pdf")
    file_type = MediaAsset.Type.DOCUMENT
    mime_type = "application/pdf"
    duration = None


class ReadyMediaAssetFactory(MediaAssetFactory):
    """Factory for ready (processed) media assets."""

    status = MediaAsset.Status.READY


class ProcessingMediaAssetFactory(MediaAssetFactory):
    """Factory for processing media assets."""

    status = MediaAsset.Status.PROCESSING


class ErrorMediaAssetFactory(MediaAssetFactory):
    """Factory for error media assets."""

    status = MediaAsset.Status.ERROR
    processing_error = "Error processing file: corrupted data"


class CourseVersionFactory(DjangoModelFactory):
    """Factory for CourseVersion model."""

    class Meta:
        model = CourseVersion

    course = factory.SubFactory(CourseFactory)
    version_number = factory.Sequence(lambda n: n + 1)
    snapshot = factory.LazyAttribute(
        lambda obj: {
            "title": obj.course.title,
            "description": obj.course.description,
            "objectives": obj.course.objectives,
            "duration": obj.course.total_duration,
            "course_type": obj.course.course_type,
            "target_profiles": obj.course.target_profiles,
            "validity_months": obj.course.validity_months,
            "modules": [],
        }
    )
    changelog = factory.Faker("sentence", locale="es_ES")
    is_major_version = False
    published_at = None
    created_by = factory.SubFactory(UserFactory)


class MajorCourseVersionFactory(CourseVersionFactory):
    """Factory for major course versions."""

    is_major_version = True
    published_at = factory.LazyFunction(timezone.now)


class ScormPackageFactory(DjangoModelFactory):
    """Factory for ScormPackage model."""

    class Meta:
        model = ScormPackage

    lesson = factory.SubFactory(ScormLessonFactory)
    package_file = factory.django.FileField(filename="scorm_package.zip")
    extracted_path = ""
    entry_point = ""
    scorm_version = ScormPackage.Version.SCORM_12
    status = ScormPackage.Status.UPLOADED
    manifest_data = factory.LazyFunction(dict)
    error_message = ""
    file_size = factory.Faker("random_int", min=1024000, max=50240000)


class ReadyScormPackageFactory(ScormPackageFactory):
    """Factory for ready SCORM packages."""

    extracted_path = factory.LazyAttribute(
        lambda obj: f"scorm_content/{obj.lesson.module.course.id}/package"
    )
    entry_point = "index.html"
    status = ScormPackage.Status.READY
    manifest_data = factory.LazyFunction(
        lambda: {
            "title": "SCORM Package",
            "version": "1.2",
            "file_count": 50,
        }
    )


class ErrorScormPackageFactory(ScormPackageFactory):
    """Factory for error SCORM packages."""

    status = ScormPackage.Status.ERROR
    error_message = "No se encontro el manifiesto SCORM (imsmanifest.xml)"


class ScormAttemptFactory(DjangoModelFactory):
    """Factory for ScormAttempt model."""

    class Meta:
        model = ScormAttempt

    enrollment = factory.SubFactory(EnrollmentFactory)
    scorm_package = factory.SubFactory(ReadyScormPackageFactory)
    attempt_number = 1
    lesson_status = ScormAttempt.Status.NOT_ATTEMPTED
    score_raw = None
    score_min = Decimal("0.00")
    score_max = Decimal("100.00")
    session_time = None
    total_time = None
    suspend_data = ""
    location = ""
    interactions = factory.LazyFunction(list)
    cmi_data = factory.LazyFunction(dict)
    completed_at = None


class InProgressScormAttemptFactory(ScormAttemptFactory):
    """Factory for in-progress SCORM attempts."""

    lesson_status = ScormAttempt.Status.INCOMPLETE
    score_raw = factory.Faker("pydecimal", min_value=0, max_value=50, right_digits=2)
    location = "page_5"


class CompletedScormAttemptFactory(ScormAttemptFactory):
    """Factory for completed SCORM attempts."""

    lesson_status = ScormAttempt.Status.COMPLETED
    score_raw = factory.Faker("pydecimal", min_value=70, max_value=100, right_digits=2)
    completed_at = factory.LazyFunction(timezone.now)


class PassedScormAttemptFactory(ScormAttemptFactory):
    """Factory for passed SCORM attempts."""

    lesson_status = ScormAttempt.Status.PASSED
    score_raw = factory.Faker("pydecimal", min_value=80, max_value=100, right_digits=2)
    completed_at = factory.LazyFunction(timezone.now)


class FailedScormAttemptFactory(ScormAttemptFactory):
    """Factory for failed SCORM attempts."""

    lesson_status = ScormAttempt.Status.FAILED
    score_raw = factory.Faker("pydecimal", min_value=0, max_value=50, right_digits=2)
    completed_at = factory.LazyFunction(timezone.now)


class ResourceLibraryFactory(DjangoModelFactory):
    """Factory for ResourceLibrary model."""

    class Meta:
        model = ResourceLibrary

    name = factory.Sequence(lambda n: f"Resource {n}")
    description = factory.Faker("paragraph", locale="es_ES")
    resource_type = ResourceLibrary.Type.IMAGE
    file = factory.django.FileField(filename="resource.jpg")
    file_size = factory.Faker("random_int", min=1024, max=10240000)
    mime_type = "image/jpeg"
    tags = factory.LazyFunction(lambda: ["seguridad", "equipos"])
    category = factory.SubFactory(CategoryFactory)
    usage_count = 0
    is_public = True
    uploaded_by = factory.SubFactory(UserFactory)


class VideoResourceFactory(ResourceLibraryFactory):
    """Factory for video resources."""

    resource_type = ResourceLibrary.Type.VIDEO
    file = factory.django.FileField(filename="resource.mp4")
    mime_type = "video/mp4"


class DocumentResourceFactory(ResourceLibraryFactory):
    """Factory for document resources."""

    resource_type = ResourceLibrary.Type.DOCUMENT
    file = factory.django.FileField(filename="resource.pdf")
    mime_type = "application/pdf"


class TemplateResourceFactory(ResourceLibraryFactory):
    """Factory for template resources."""

    resource_type = ResourceLibrary.Type.TEMPLATE
    file = factory.django.FileField(filename="template.docx")
    mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class InfographicResourceFactory(ResourceLibraryFactory):
    """Factory for infographic resources."""

    resource_type = ResourceLibrary.Type.INFOGRAPHIC
    file = factory.django.FileField(filename="infographic.png")
    mime_type = "image/png"


# Helper factories for creating complex test scenarios


class CourseWithModulesFactory(CourseFactory):
    """Factory for courses with modules."""

    @factory.post_generation
    def modules(self, create, extracted, **kwargs):
        if not create:
            return

        if extracted:
            for module in extracted:
                module.course = self
                module.save()
        else:
            # Create 3 modules by default
            for i in range(3):
                ModuleFactory(course=self, order=i)


class ModuleWithLessonsFactory(ModuleFactory):
    """Factory for modules with lessons."""

    @factory.post_generation
    def lessons(self, create, extracted, **kwargs):
        if not create:
            return

        if extracted:
            for lesson in extracted:
                lesson.module = self
                lesson.save()
        else:
            # Create 5 lessons by default with varied types
            lesson_types = [
                Lesson.Type.VIDEO,
                Lesson.Type.PDF,
                Lesson.Type.TEXT,
                Lesson.Type.QUIZ,
                Lesson.Type.INTERACTIVE,
            ]
            for i, lesson_type in enumerate(lesson_types):
                LessonFactory(module=self, order=i, lesson_type=lesson_type)


class FullCourseFactory(CourseFactory):
    """Factory for a complete course with modules and lessons."""

    @factory.post_generation
    def full_content(self, create, extracted, **kwargs):
        if not create:
            return

        # Create 3 modules, each with 4 lessons
        for i in range(3):
            module = ModuleFactory(course=self, order=i, title=f"Module {i + 1}")
            for j in range(4):
                lesson_types = [
                    Lesson.Type.VIDEO,
                    Lesson.Type.PDF,
                    Lesson.Type.TEXT,
                    Lesson.Type.QUIZ,
                ]
                LessonFactory(
                    module=module,
                    order=j,
                    title=f"Lesson {j + 1}",
                    lesson_type=lesson_types[j % len(lesson_types)],
                )


class EnrollmentWithProgressFactory(EnrollmentFactory):
    """Factory for enrollment with lesson progress."""

    @factory.post_generation
    def with_progress(self, create, extracted, **kwargs):
        if not create:
            return

        # Create progress for all lessons in the course
        completed_count = extracted if extracted else 0
        lessons = Lesson.objects.filter(module__course=self.course).order_by(
            "module__order", "order"
        )

        for i, lesson in enumerate(lessons):
            if i < completed_count:
                CompletedLessonProgressFactory(enrollment=self, lesson=lesson)
            else:
                LessonProgressFactory(enrollment=self, lesson=lesson)
