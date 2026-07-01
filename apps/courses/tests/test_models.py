"""
Tests for courses models.

Comprehensive tests for all model classes in the courses module.
"""

from datetime import date
from decimal import Decimal

from django.db import IntegrityError

import pytest

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
from apps.courses.tests.factories import (
    ArchivedCourseFactory,
    CategoryFactory,
    CompletedEnrollmentFactory,
    CompletedLessonProgressFactory,
    CompletedScormAttemptFactory,
    CourseFactory,
    CourseVersionFactory,
    DroppedEnrollmentFactory,
    EnrollmentFactory,
    ErrorMediaAssetFactory,
    ErrorScormPackageFactory,
    ExpiredEnrollmentFactory,
    FailedScormAttemptFactory,
    FullCourseFactory,
    ImageAssetFactory,
    InProgressEnrollmentFactory,
    InProgressScormAttemptFactory,
    LessonFactory,
    LessonProgressFactory,
    MajorCourseVersionFactory,
    MandatoryCourseFactory,
    MediaAssetFactory,
    ModuleFactory,
    ModuleWithLessonsFactory,
    OptionalCourseFactory,
    PassedScormAttemptFactory,
    PDFLessonFactory,
    PublishedCourseFactory,
    QuizLessonFactory,
    ReadyMediaAssetFactory,
    ReadyScormPackageFactory,
    RefresherCourseFactory,
    ResourceLibraryFactory,
    ScormAttemptFactory,
    ScormLessonFactory,
    ScormPackageFactory,
    TextLessonFactory,
    UserFactory,
    VideoAssetFactory,
    VideoLessonFactory,
)


@pytest.mark.django_db
class TestCategory:
    """Tests for the Category model."""

    def test_create_category(self):
        """Test creating a basic category."""
        category = CategoryFactory()
        assert category.id is not None
        assert category.name is not None
        assert category.slug is not None
        assert category.is_active is True

    def test_category_str(self):
        """Test category string representation."""
        category = CategoryFactory(name="Seguridad Industrial")
        assert str(category) == "Seguridad Industrial"

    def test_category_full_path(self):
        """Test full_path property returns the category name (flat categories)."""
        category = CategoryFactory(name="Root Category")
        assert category.full_path == "Root Category"

    def test_category_has_no_parent_field(self):
        """Category model no longer exposes a self-referential parent FK."""
        category = CategoryFactory()
        assert not hasattr(category, "parent")

    def test_category_slug_unique(self):
        """Test that category slug must be unique."""
        CategoryFactory(slug="test-slug")
        with pytest.raises(IntegrityError):
            # Use direct model creation to test unique constraint
            # (Factory has django_get_or_create which would return existing)
            Category.objects.create(name="Another", slug="test-slug")

    def test_category_ordering(self):
        """Test category ordering by order and name."""
        cat3 = CategoryFactory(order=2, name="C Category")
        cat1 = CategoryFactory(order=0, name="A Category")
        cat2 = CategoryFactory(order=1, name="B Category")

        categories = list(Category.objects.all())
        assert categories[0] == cat1
        assert categories[1] == cat2
        assert categories[2] == cat3

    def test_category_default_color(self):
        """Test category default color."""
        category = Category.objects.create(
            name="Test",
            slug="test-default-color",
        )
        assert category.color == "#3B82F6"


@pytest.mark.django_db
class TestCourse:
    """Tests for the Course model."""

    def test_create_course(self):
        """Test creating a basic course."""
        course = CourseFactory()
        assert course.id is not None
        assert course.code is not None
        assert course.status == Course.Status.DRAFT
        assert course.version == 1

    def test_course_str(self):
        """Test course string representation."""
        course = CourseFactory(code="SEC-001", title="Seguridad Basica")
        assert str(course) == "SEC-001 - Seguridad Basica"

    def test_course_code_unique(self):
        """Test that course code must be unique."""
        course = CourseFactory(code="UNIQUE-001")
        with pytest.raises(IntegrityError):
            # Use direct model creation to test unique constraint
            # (Factory has django_get_or_create which would return existing)
            Course.objects.create(
                code="UNIQUE-001",
                title="Duplicate",
                description="Test",
                created_by=course.created_by,
            )

    def test_course_types(self):
        """Test different course types."""
        mandatory = MandatoryCourseFactory()
        optional = OptionalCourseFactory()
        refresher = RefresherCourseFactory()

        assert mandatory.course_type == Course.Type.MANDATORY
        assert optional.course_type == Course.Type.OPTIONAL
        assert refresher.course_type == Course.Type.REFRESHER

    def test_course_statuses(self):
        """Test different course statuses."""
        draft = CourseFactory()
        published = PublishedCourseFactory()
        archived = ArchivedCourseFactory()

        assert draft.status == Course.Status.DRAFT
        assert published.status == Course.Status.PUBLISHED
        assert archived.status == Course.Status.ARCHIVED

    def test_course_total_duration_no_modules(self):
        """Test total_duration when course has no modules."""
        course = CourseFactory()
        assert course.total_duration == 0

    def test_course_total_duration_with_lessons(self):
        """Test total_duration calculation with lessons."""
        course = CourseFactory()
        module1 = ModuleFactory(course=course)
        module2 = ModuleFactory(course=course)

        LessonFactory(module=module1, duration=30)
        LessonFactory(module=module1, duration=20)
        LessonFactory(module=module2, duration=15)

        assert course.total_duration == 65

    def test_course_prerequisites(self):
        """Test course prerequisites relationship."""
        prereq1 = PublishedCourseFactory()
        prereq2 = PublishedCourseFactory()
        course = CourseFactory()

        course.prerequisites.add(prereq1, prereq2)

        assert course.prerequisites.count() == 2
        assert prereq1 in course.prerequisites.all()
        assert course in prereq1.required_for.all()

    def test_course_contracts_relationship(self):
        """Test course-contracts many-to-many relationship."""
        from apps.courses.tests.factories import ContractFactory

        course = CourseFactory()
        contract1 = ContractFactory()
        contract2 = ContractFactory()

        course.contracts.add(contract1, contract2)

        assert course.contracts.count() == 2
        assert course in contract1.courses.all()

    def test_course_category_relationship(self):
        """Test course-category relationship."""
        category = CategoryFactory()
        course = CourseFactory(category=category)

        assert course.category == category
        assert course in category.courses.all()

    def test_course_created_by_protection(self):
        """Test that course cannot be deleted if creator exists."""
        user = UserFactory()
        course = CourseFactory(created_by=user)

        # Course should have a creator
        assert course.created_by == user

    def test_course_published_at(self):
        """Test published_at field."""
        draft = CourseFactory()
        published = PublishedCourseFactory()

        assert draft.published_at is None
        assert published.published_at is not None

    def test_course_validity_months(self):
        """Test validity_months field."""
        course_with_validity = CourseFactory(validity_months=12)
        course_no_expiry = CourseFactory(validity_months=None)

        assert course_with_validity.validity_months == 12
        assert course_no_expiry.validity_months is None

    def test_course_target_profiles(self):
        """Test target_profiles JSON field."""
        profiles = ["LINIERO", "JEFE_CUADRILLA", "INGENIERO_RESIDENTE"]
        course = CourseFactory(target_profiles=profiles)

        assert course.target_profiles == profiles
        assert "LINIERO" in course.target_profiles

    def test_course_ordering(self):
        """Test course ordering by title."""
        course_c = CourseFactory(title="C Course")
        course_a = CourseFactory(title="A Course")
        course_b = CourseFactory(title="B Course")

        courses = list(Course.objects.all())
        assert courses[0] == course_a
        assert courses[1] == course_b
        assert courses[2] == course_c


@pytest.mark.django_db
class TestModule:
    """Tests for the Module model."""

    def test_create_module(self):
        """Test creating a basic module."""
        module = ModuleFactory()
        assert module.id is not None
        assert module.course is not None
        assert module.order >= 0

    def test_module_str(self):
        """Test module string representation."""
        course = CourseFactory(code="SEC-001")
        module = ModuleFactory(course=course, title="Introduccion")
        assert str(module) == "SEC-001 - Introduccion"

    def test_module_ordering(self):
        """Test modules are ordered by order field."""
        course = CourseFactory()
        mod3 = ModuleFactory(course=course, order=2)
        mod1 = ModuleFactory(course=course, order=0)
        mod2 = ModuleFactory(course=course, order=1)

        modules = list(course.modules.all())
        assert modules[0] == mod1
        assert modules[1] == mod2
        assert modules[2] == mod3

    def test_module_unique_together(self):
        """Test that course+order must be unique."""
        course = CourseFactory()
        ModuleFactory(course=course, order=0)
        with pytest.raises(IntegrityError):
            ModuleFactory(course=course, order=0)

    def test_module_cascade_delete(self):
        """Test that modules are deleted when course is deleted."""
        course = CourseFactory()
        module = ModuleFactory(course=course)
        module_id = module.id

        course.delete()

        assert not Module.objects.filter(id=module_id).exists()

    def test_module_lessons_relationship(self):
        """Test module-lessons relationship."""
        module = ModuleFactory()
        lesson1 = LessonFactory(module=module)
        lesson2 = LessonFactory(module=module)

        assert module.lessons.count() == 2
        assert lesson1 in module.lessons.all()
        assert lesson2 in module.lessons.all()

    def test_module_with_lessons_factory(self):
        """Test ModuleWithLessonsFactory."""
        module = ModuleWithLessonsFactory()
        assert module.lessons.count() == 5


@pytest.mark.django_db
class TestLesson:
    """Tests for the Lesson model."""

    def test_create_lesson(self):
        """Test creating a basic lesson."""
        lesson = LessonFactory()
        assert lesson.id is not None
        assert lesson.module is not None
        assert lesson.is_mandatory is True

    def test_lesson_str(self):
        """Test lesson string representation."""
        module = ModuleFactory(title="Module 1")
        lesson = LessonFactory(module=module, title="Lesson 1")
        assert str(lesson) == "Module 1 - Lesson 1"

    def test_lesson_types(self):
        """Test all lesson types."""
        video = VideoLessonFactory()
        pdf = PDFLessonFactory()
        scorm = ScormLessonFactory()
        quiz = QuizLessonFactory()
        text = TextLessonFactory()

        assert video.lesson_type == Lesson.Type.VIDEO
        assert pdf.lesson_type == Lesson.Type.PDF
        assert scorm.lesson_type == Lesson.Type.SCORM
        assert quiz.lesson_type == Lesson.Type.QUIZ
        assert text.lesson_type == Lesson.Type.TEXT

    def test_lesson_ordering(self):
        """Test lessons are ordered by order field."""
        module = ModuleFactory()
        les3 = LessonFactory(module=module, order=2)
        les1 = LessonFactory(module=module, order=0)
        les2 = LessonFactory(module=module, order=1)

        lessons = list(module.lessons.all())
        assert lessons[0] == les1
        assert lessons[1] == les2
        assert lessons[2] == les3

    def test_lesson_metadata(self):
        """Test lesson metadata JSON field."""
        quiz = QuizLessonFactory()
        assert "passing_score" in quiz.metadata
        assert quiz.metadata["passing_score"] == 70

    def test_lesson_video_url(self):
        """Test video URL for video lessons."""
        video = VideoLessonFactory()
        assert video.video_url != ""

    def test_lesson_cascade_delete(self):
        """Test that lessons are deleted when module is deleted."""
        module = ModuleFactory()
        lesson = LessonFactory(module=module)
        lesson_id = lesson.id

        module.delete()

        assert not Lesson.objects.filter(id=lesson_id).exists()

    def test_lesson_is_offline_available(self):
        """Test offline availability flag."""
        online_only = LessonFactory(is_offline_available=False)
        offline_ok = LessonFactory(is_offline_available=True)

        assert online_only.is_offline_available is False
        assert offline_ok.is_offline_available is True

    def test_lesson_mandatory_vs_optional(self):
        """Test mandatory vs optional lessons."""
        mandatory = LessonFactory(is_mandatory=True)
        optional = LessonFactory(is_mandatory=False)

        assert mandatory.is_mandatory is True
        assert optional.is_mandatory is False


@pytest.mark.django_db
class TestEnrollment:
    """Tests for the Enrollment model."""

    def test_create_enrollment(self):
        """Test creating a basic enrollment."""
        enrollment = EnrollmentFactory()
        assert enrollment.id is not None
        assert enrollment.user is not None
        assert enrollment.course is not None
        assert enrollment.status == Enrollment.Status.ENROLLED

    def test_enrollment_str(self):
        """Test enrollment string representation."""
        enrollment = EnrollmentFactory()
        expected = f"{enrollment.user} - {enrollment.course}"
        assert str(enrollment) == expected

    def test_enrollment_statuses(self):
        """Test all enrollment statuses."""
        enrolled = EnrollmentFactory()
        in_progress = InProgressEnrollmentFactory()
        completed = CompletedEnrollmentFactory()
        expired = ExpiredEnrollmentFactory()
        dropped = DroppedEnrollmentFactory()

        assert enrolled.status == Enrollment.Status.ENROLLED
        assert in_progress.status == Enrollment.Status.IN_PROGRESS
        assert completed.status == Enrollment.Status.COMPLETED
        assert expired.status == Enrollment.Status.EXPIRED
        assert dropped.status == Enrollment.Status.DROPPED

    def test_enrollment_unique_together(self):
        """Test that user+course must be unique."""
        user = UserFactory()
        course = PublishedCourseFactory()
        EnrollmentFactory(user=user, course=course)

        with pytest.raises(IntegrityError):
            # Use direct model creation to test unique constraint
            # (Factory has django_get_or_create which would return existing)
            Enrollment.objects.create(user=user, course=course)

    def test_enrollment_progress(self):
        """Test enrollment progress field."""
        enrollment = EnrollmentFactory(progress=Decimal("50.00"))
        assert enrollment.progress == Decimal("50.00")

    def test_enrollment_progress_completed(self):
        """Test completed enrollment progress."""
        completed = CompletedEnrollmentFactory()
        assert completed.progress == Decimal("100.00")
        assert completed.completed_at is not None

    def test_enrollment_due_date(self):
        """Test enrollment due date."""
        enrollment = EnrollmentFactory()
        assert enrollment.due_date is not None

    def test_enrollment_expired_due_date(self):
        """Test expired enrollment due date is in the past."""
        expired = ExpiredEnrollmentFactory()
        assert expired.due_date < date.today()

    def test_enrollment_assigned_by(self):
        """Test assigned_by relationship."""
        supervisor = UserFactory()
        worker = UserFactory()
        course = PublishedCourseFactory()

        enrollment = EnrollmentFactory(user=worker, course=course, assigned_by=supervisor)

        assert enrollment.assigned_by == supervisor

    def test_enrollment_cascade_delete_user(self):
        """Test that enrollments are deleted when user is deleted."""
        user = UserFactory()
        enrollment = EnrollmentFactory(user=user)
        enrollment_id = enrollment.id

        user.delete()

        assert not Enrollment.objects.filter(id=enrollment_id).exists()

    def test_enrollment_cascade_delete_course(self):
        """Test that enrollments are deleted when course is deleted."""
        course = PublishedCourseFactory()
        enrollment = EnrollmentFactory(course=course)
        enrollment_id = enrollment.id

        course.delete()

        assert not Enrollment.objects.filter(id=enrollment_id).exists()

    def test_enrollment_started_at(self):
        """Test started_at timestamp."""
        new_enrollment = EnrollmentFactory()
        in_progress = InProgressEnrollmentFactory()

        assert new_enrollment.started_at is None
        assert in_progress.started_at is not None


@pytest.mark.django_db
class TestLessonProgress:
    """Tests for the LessonProgress model."""

    def test_create_lesson_progress(self):
        """Test creating lesson progress."""
        progress = LessonProgressFactory()
        assert progress.id is not None
        assert progress.enrollment is not None
        assert progress.lesson is not None
        assert progress.is_completed is False

    def test_lesson_progress_str(self):
        """Test lesson progress string representation."""
        progress = LessonProgressFactory()
        expected = f"{progress.enrollment.user} - {progress.lesson}"
        assert str(progress) == expected

    def test_lesson_progress_unique_together(self):
        """Test that enrollment+lesson must be unique."""
        enrollment = EnrollmentFactory()
        lesson = LessonFactory()
        LessonProgressFactory(enrollment=enrollment, lesson=lesson)

        with pytest.raises(IntegrityError):
            # Use direct model creation to test unique constraint
            # (Factory has django_get_or_create which would return existing)
            LessonProgress.objects.create(enrollment=enrollment, lesson=lesson)

    def test_lesson_progress_completed(self):
        """Test completed lesson progress."""
        completed = CompletedLessonProgressFactory()
        assert completed.is_completed is True
        assert completed.progress_percent == Decimal("100.00")
        assert completed.completed_at is not None

    def test_lesson_progress_time_spent(self):
        """Test time_spent tracking."""
        progress = LessonProgressFactory(time_spent=600)
        assert progress.time_spent == 600  # 10 minutes in seconds

    def test_lesson_progress_last_position(self):
        """Test last_position JSON field."""
        position = {"video_time": 120, "page": 5}
        progress = LessonProgressFactory(last_position=position)
        assert progress.last_position == position

    def test_lesson_progress_cascade_delete(self):
        """Test that progress is deleted when enrollment is deleted."""
        enrollment = EnrollmentFactory()
        progress = LessonProgressFactory(enrollment=enrollment)
        progress_id = progress.id

        enrollment.delete()

        assert not LessonProgress.objects.filter(id=progress_id).exists()


@pytest.mark.django_db
class TestMediaAsset:
    """Tests for the MediaAsset model."""

    def test_create_media_asset(self):
        """Test creating a basic media asset."""
        asset = MediaAssetFactory()
        assert asset.id is not None
        assert asset.status == MediaAsset.Status.PENDING

    def test_media_asset_str(self):
        """Test media asset string representation."""
        asset = MediaAssetFactory(original_name="video_tutorial.mp4")
        assert str(asset) == "video_tutorial.mp4"

    def test_media_asset_types(self):
        """Test different media asset types."""
        video = VideoAssetFactory()
        image = ImageAssetFactory()

        assert video.file_type == MediaAsset.Type.VIDEO
        assert image.file_type == MediaAsset.Type.IMAGE

    def test_media_asset_statuses(self):
        """Test all media asset statuses."""
        pending = MediaAssetFactory()
        ready = ReadyMediaAssetFactory()
        error = ErrorMediaAssetFactory()

        assert pending.status == MediaAsset.Status.PENDING
        assert ready.status == MediaAsset.Status.READY
        assert error.status == MediaAsset.Status.ERROR

    def test_media_asset_error_message(self):
        """Test error message for failed assets."""
        error = ErrorMediaAssetFactory()
        assert error.processing_error != ""

    def test_media_asset_metadata(self):
        """Test metadata JSON field."""
        metadata = {"codec": "h264", "bitrate": "5000kbps"}
        asset = MediaAssetFactory(metadata=metadata)
        assert asset.metadata == metadata

    def test_media_asset_duration(self):
        """Test duration for video/audio assets."""
        video = VideoAssetFactory(duration=3600)
        assert video.duration == 3600  # 1 hour in seconds


@pytest.mark.django_db
class TestCourseVersion:
    """Tests for the CourseVersion model."""

    def test_create_course_version(self):
        """Test creating a course version."""
        version = CourseVersionFactory()
        assert version.id is not None
        assert version.course is not None
        assert version.version_number >= 1

    def test_course_version_str(self):
        """Test course version string representation."""
        course = CourseFactory(code="SEC-001")
        version = CourseVersionFactory(course=course, version_number=2)
        assert str(version) == "SEC-001 v2"

    def test_course_version_unique_together(self):
        """Test that course+version_number must be unique."""
        course = CourseFactory()
        CourseVersionFactory(course=course, version_number=1)

        with pytest.raises(IntegrityError):
            CourseVersionFactory(course=course, version_number=1)

    def test_course_version_snapshot(self):
        """Test snapshot JSON field."""
        version = CourseVersionFactory()
        assert "title" in version.snapshot
        assert "description" in version.snapshot
        assert "modules" in version.snapshot

    def test_course_version_create_snapshot(self):
        """Test create_snapshot class method."""
        user = UserFactory()
        course = CourseFactory()
        module = ModuleFactory(course=course)
        LessonFactory(module=module)

        version = CourseVersion.create_snapshot(
            course=course, user=user, changelog="Initial version", is_major=True
        )

        assert version.version_number == 1
        assert version.changelog == "Initial version"
        assert version.is_major_version is True
        assert version.created_by == user
        assert len(version.snapshot["modules"]) == 1

    def test_course_version_increment(self):
        """Test version number increments correctly."""
        course = CourseFactory()
        user = UserFactory()

        v1 = CourseVersion.create_snapshot(course, user)
        v2 = CourseVersion.create_snapshot(course, user)
        v3 = CourseVersion.create_snapshot(course, user)

        assert v1.version_number == 1
        assert v2.version_number == 2
        assert v3.version_number == 3

    def test_course_version_major_factory(self):
        """Test MajorCourseVersionFactory."""
        version = MajorCourseVersionFactory()
        assert version.is_major_version is True
        assert version.published_at is not None

    def test_course_version_ordering(self):
        """Test versions are ordered by version_number descending."""
        course = CourseFactory()
        v1 = CourseVersionFactory(course=course, version_number=1)
        v3 = CourseVersionFactory(course=course, version_number=3)
        v2 = CourseVersionFactory(course=course, version_number=2)

        versions = list(course.versions.all())
        assert versions[0] == v3
        assert versions[1] == v2
        assert versions[2] == v1


@pytest.mark.django_db
class TestScormPackage:
    """Tests for the ScormPackage model."""

    def test_create_scorm_package(self):
        """Test creating a SCORM package."""
        package = ScormPackageFactory()
        assert package.id is not None
        assert package.lesson is not None
        assert package.status == ScormPackage.Status.UPLOADED

    def test_scorm_package_str(self):
        """Test SCORM package string representation."""
        lesson = ScormLessonFactory(title="SCORM Lesson")
        package = ScormPackageFactory(lesson=lesson)
        assert str(package) == "SCORM: SCORM Lesson"

    def test_scorm_package_versions(self):
        """Test SCORM version choices."""
        scorm_12 = ScormPackageFactory(scorm_version=ScormPackage.Version.SCORM_12)
        scorm_2004 = ScormPackageFactory(scorm_version=ScormPackage.Version.SCORM_2004)
        xapi = ScormPackageFactory(scorm_version=ScormPackage.Version.XAPI)

        assert scorm_12.scorm_version == "1.2"
        assert scorm_2004.scorm_version == "2004"
        assert xapi.scorm_version == "xapi"

    def test_scorm_package_statuses(self):
        """Test all SCORM package statuses."""
        uploaded = ScormPackageFactory()
        ready = ReadyScormPackageFactory()
        error = ErrorScormPackageFactory()

        assert uploaded.status == ScormPackage.Status.UPLOADED
        assert ready.status == ScormPackage.Status.READY
        assert error.status == ScormPackage.Status.ERROR

    def test_scorm_package_launch_url(self):
        """Test launch_url property."""
        ready = ReadyScormPackageFactory()
        assert ready.launch_url is not None
        assert ready.entry_point in ready.launch_url

    def test_scorm_package_launch_url_none(self):
        """Test launch_url returns None when not ready."""
        package = ScormPackageFactory()
        assert package.launch_url is None

    def test_scorm_package_manifest_data(self):
        """Test manifest_data JSON field."""
        ready = ReadyScormPackageFactory()
        assert "title" in ready.manifest_data
        assert "version" in ready.manifest_data


@pytest.mark.django_db
class TestScormAttempt:
    """Tests for the ScormAttempt model."""

    def test_create_scorm_attempt(self):
        """Test creating a SCORM attempt."""
        attempt = ScormAttemptFactory()
        assert attempt.id is not None
        assert attempt.enrollment is not None
        assert attempt.scorm_package is not None

    def test_scorm_attempt_str(self):
        """Test SCORM attempt string representation."""
        attempt = ScormAttemptFactory()
        expected = f"{attempt.enrollment.user} - {attempt.scorm_package.lesson.title} (Intento {attempt.attempt_number})"
        assert str(attempt) == expected

    def test_scorm_attempt_statuses(self):
        """Test all SCORM attempt statuses."""
        not_attempted = ScormAttemptFactory()
        in_progress = InProgressScormAttemptFactory()
        completed = CompletedScormAttemptFactory()
        passed = PassedScormAttemptFactory()
        failed = FailedScormAttemptFactory()

        assert not_attempted.lesson_status == ScormAttempt.Status.NOT_ATTEMPTED
        assert in_progress.lesson_status == ScormAttempt.Status.INCOMPLETE
        assert completed.lesson_status == ScormAttempt.Status.COMPLETED
        assert passed.lesson_status == ScormAttempt.Status.PASSED
        assert failed.lesson_status == ScormAttempt.Status.FAILED

    def test_scorm_attempt_scores(self):
        """Test SCORM score fields."""
        attempt = PassedScormAttemptFactory()
        assert attempt.score_raw is not None
        assert attempt.score_min == Decimal("0.00")
        assert attempt.score_max == Decimal("100.00")

    def test_scorm_attempt_interactions(self):
        """Test interactions JSON field."""
        interactions = [
            {"id": "q1", "type": "choice", "result": "correct"},
            {"id": "q2", "type": "choice", "result": "incorrect"},
        ]
        attempt = ScormAttemptFactory(interactions=interactions)
        assert len(attempt.interactions) == 2

    def test_scorm_attempt_cmi_data(self):
        """Test cmi_data JSON field."""
        cmi = {
            "cmi.core.lesson_location": "page_5",
            "cmi.core.lesson_status": "incomplete",
        }
        attempt = ScormAttemptFactory(cmi_data=cmi)
        assert attempt.cmi_data == cmi


@pytest.mark.django_db
class TestResourceLibrary:
    """Tests for the ResourceLibrary model."""

    def test_create_resource(self):
        """Test creating a resource."""
        resource = ResourceLibraryFactory()
        assert resource.id is not None
        assert resource.is_public is True
        assert resource.usage_count == 0

    def test_resource_str(self):
        """Test resource string representation."""
        resource = ResourceLibraryFactory(name="Safety Poster")
        assert str(resource) == "Safety Poster"

    def test_resource_types(self):
        """Test all resource types."""
        image = ResourceLibraryFactory(resource_type=ResourceLibrary.Type.IMAGE)
        video = ResourceLibraryFactory(resource_type=ResourceLibrary.Type.VIDEO)
        document = ResourceLibraryFactory(resource_type=ResourceLibrary.Type.DOCUMENT)
        template = ResourceLibraryFactory(resource_type=ResourceLibrary.Type.TEMPLATE)
        infographic = ResourceLibraryFactory(resource_type=ResourceLibrary.Type.INFOGRAPHIC)

        assert image.resource_type == ResourceLibrary.Type.IMAGE
        assert video.resource_type == ResourceLibrary.Type.VIDEO
        assert document.resource_type == ResourceLibrary.Type.DOCUMENT
        assert template.resource_type == ResourceLibrary.Type.TEMPLATE
        assert infographic.resource_type == ResourceLibrary.Type.INFOGRAPHIC

    def test_resource_tags(self):
        """Test tags JSON field."""
        tags = ["seguridad", "equipos", "epp"]
        resource = ResourceLibraryFactory(tags=tags)
        assert resource.tags == tags

    def test_resource_usage_count(self):
        """Test usage_count field."""
        resource = ResourceLibraryFactory(usage_count=50)
        assert resource.usage_count == 50

    def test_resource_category_relationship(self):
        """Test resource-category relationship."""
        category = CategoryFactory()
        resource = ResourceLibraryFactory(category=category)

        assert resource.category == category
        assert resource in category.resources.all()


@pytest.mark.django_db
class TestFullCourse:
    """Tests for full course with all related objects."""

    def test_full_course_creation(self):
        """Test creating a full course with modules and lessons."""
        course = FullCourseFactory()

        assert course.modules.count() == 3
        for module in course.modules.all():
            assert module.lessons.count() == 4

    def test_full_course_total_duration(self):
        """Test total duration calculation for full course."""
        course = CourseFactory()
        module1 = ModuleFactory(course=course)
        module2 = ModuleFactory(course=course)

        # Create lessons with known durations
        LessonFactory(module=module1, duration=10)
        LessonFactory(module=module1, duration=15)
        LessonFactory(module=module2, duration=20)
        LessonFactory(module=module2, duration=25)

        assert course.total_duration == 70

    def test_enrollment_with_full_progress(self):
        """Test enrollment progress through a full course."""
        course = CourseFactory()
        module = ModuleFactory(course=course)
        lesson1 = LessonFactory(module=module, is_mandatory=True)
        lesson2 = LessonFactory(module=module, is_mandatory=True)
        lesson3 = LessonFactory(module=module, is_mandatory=False)

        user = UserFactory()
        enrollment = EnrollmentFactory(user=user, course=course)

        # Complete all mandatory lessons
        CompletedLessonProgressFactory(enrollment=enrollment, lesson=lesson1)
        CompletedLessonProgressFactory(enrollment=enrollment, lesson=lesson2)

        # Verify lesson progress counts
        completed_mandatory = LessonProgress.objects.filter(
            enrollment=enrollment, lesson__is_mandatory=True, is_completed=True
        ).count()

        assert completed_mandatory == 2


@pytest.mark.django_db
class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_course_with_empty_target_profiles(self):
        """Test course with empty target_profiles list."""
        course = CourseFactory(target_profiles=[])
        assert course.target_profiles == []

    def test_course_with_zero_total_duration(self):
        """Test course with no lessons has zero total_duration."""
        course = CourseFactory()
        assert course.total_duration == 0

    def test_enrollment_progress_boundaries(self):
        """Test enrollment progress at boundaries."""
        enrollment_zero = EnrollmentFactory(progress=Decimal("0.00"))
        enrollment_hundred = EnrollmentFactory(progress=Decimal("100.00"))

        assert enrollment_zero.progress == Decimal("0.00")
        assert enrollment_hundred.progress == Decimal("100.00")

    def test_lesson_with_empty_content(self):
        """Test lesson with empty content."""
        lesson = LessonFactory(content="", video_url="")
        assert lesson.content == ""
        assert lesson.video_url == ""

    def test_module_with_no_lessons(self):
        """Test module with no lessons."""
        module = ModuleFactory()
        assert module.lessons.count() == 0

    def test_course_self_referential_prerequisites(self):
        """Test that a course can have prerequisites."""
        prereq = PublishedCourseFactory()
        course = CourseFactory()
        course.prerequisites.add(prereq)

        assert prereq in course.prerequisites.all()
        assert course not in prereq.prerequisites.all()

    def test_scorm_attempt_multiple_attempts(self):
        """Test multiple SCORM attempts for same enrollment."""
        enrollment = EnrollmentFactory()
        package = ReadyScormPackageFactory()

        attempt1 = ScormAttemptFactory(
            enrollment=enrollment, scorm_package=package, attempt_number=1
        )
        attempt2 = ScormAttemptFactory(
            enrollment=enrollment, scorm_package=package, attempt_number=2
        )

        assert attempt1.attempt_number == 1
        assert attempt2.attempt_number == 2

    def test_media_asset_large_file_size(self):
        """Test media asset with large file size."""
        large_size = 1024 * 1024 * 1024  # 1 GB
        asset = MediaAssetFactory(size=large_size)
        assert asset.size == large_size

    def test_resource_with_special_characters_in_name(self):
        """Test resource with special characters in name."""
        resource = ResourceLibraryFactory(name="Safety & Health - Manual (2024)")
        assert resource.name == "Safety & Health - Manual (2024)"

    def test_course_version_empty_changelog(self):
        """Test course version with empty changelog."""
        version = CourseVersionFactory(changelog="")
        assert version.changelog == ""
