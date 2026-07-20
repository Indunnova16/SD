"""
Factory classes for sync tests.

Uses factory_boy to create test data for all sync models.
"""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.utils import timezone

import factory
from factory.django import DjangoModelFactory

from apps.courses.models import Course
from apps.courses.tests.factories import JobProfileTypeFactory
from apps.sync.models import (
    OfflinePackage,
    PackageDownload,
    SyncConflict,
    SyncLog,
)

User = get_user_model()


class UserFactory(DjangoModelFactory):
    """Factory for User model."""

    class Meta:
        model = User
        django_get_or_create = ("email",)

    email = factory.Sequence(lambda n: f"syncuser{n}@test.com")
    password = factory.PostGenerationMethodCall("set_password", "testpass123")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    document_type = "CC"
    document_number = factory.Sequence(lambda n: f"{50000000 + n}")
    job_position = "Technician"
    job_profile = factory.SubFactory(JobProfileTypeFactory)
    hire_date = factory.LazyFunction(lambda: date.today() - timedelta(days=365))
    is_active = True


class AdminUserFactory(UserFactory):
    """Factory for admin users."""

    email = factory.Sequence(lambda n: f"syncadmin{n}@test.com")
    is_staff = True
    is_superuser = False


class SuperUserFactory(UserFactory):
    """Factory for superusers."""

    email = factory.Sequence(lambda n: f"syncsuperuser{n}@test.com")
    is_staff = True
    is_superuser = True


class CourseFactory(DjangoModelFactory):
    """Factory for Course model."""

    class Meta:
        model = Course
        django_get_or_create = ("code",)

    code = factory.Sequence(lambda n: f"SYNC-COURSE-{n:04d}")
    title = factory.Sequence(lambda n: f"Test Course {n}")
    description = factory.Faker("paragraph")
    objectives = factory.Faker("paragraph")
    course_type = Course.Type.MANDATORY
    status = Course.Status.PUBLISHED
    created_by = factory.SubFactory(UserFactory)


class SyncLogFactory(DjangoModelFactory):
    """Factory for SyncLog model."""

    class Meta:
        model = SyncLog

    user = factory.SubFactory(UserFactory)
    device_id = factory.Sequence(lambda n: f"device-{n:06d}")
    device_name = factory.Sequence(lambda n: f"Test Device {n}")
    direction = SyncLog.Direction.BIDIRECTIONAL
    status = SyncLog.Status.PENDING
    started_at = None
    completed_at = None
    records_uploaded = 0
    records_downloaded = 0
    bytes_transferred = 0
    error_message = ""
    error_details = factory.LazyFunction(dict)
    client_timestamp = None
    metadata = factory.LazyFunction(dict)


class PendingSyncLogFactory(SyncLogFactory):
    """Factory for pending sync logs."""

    status = SyncLog.Status.PENDING
    started_at = None
    completed_at = None


class InProgressSyncLogFactory(SyncLogFactory):
    """Factory for in-progress sync logs."""

    status = SyncLog.Status.IN_PROGRESS
    started_at = factory.LazyFunction(timezone.now)
    completed_at = None


class CompletedSyncLogFactory(SyncLogFactory):
    """Factory for completed sync logs."""

    status = SyncLog.Status.COMPLETED
    started_at = factory.LazyFunction(lambda: timezone.now() - timedelta(minutes=5))
    completed_at = factory.LazyFunction(timezone.now)
    records_uploaded = factory.Faker("random_int", min=10, max=100)
    records_downloaded = factory.Faker("random_int", min=10, max=100)
    bytes_transferred = factory.Faker("random_int", min=1024, max=1048576)


class FailedSyncLogFactory(SyncLogFactory):
    """Factory for failed sync logs."""

    status = SyncLog.Status.FAILED
    started_at = factory.LazyFunction(lambda: timezone.now() - timedelta(minutes=5))
    completed_at = factory.LazyFunction(timezone.now)
    error_message = "Sync failed due to network error"
    error_details = factory.LazyFunction(
        lambda: {"code": "NETWORK_ERROR", "details": "Connection timeout"}
    )


class PartialSyncLogFactory(SyncLogFactory):
    """Factory for partial sync logs (with conflicts)."""

    status = SyncLog.Status.PARTIAL
    started_at = factory.LazyFunction(lambda: timezone.now() - timedelta(minutes=5))
    completed_at = factory.LazyFunction(timezone.now)
    records_uploaded = factory.Faker("random_int", min=5, max=50)
    records_downloaded = factory.Faker("random_int", min=5, max=50)


class UploadSyncLogFactory(SyncLogFactory):
    """Factory for upload-only sync logs."""

    direction = SyncLog.Direction.UPLOAD


class DownloadSyncLogFactory(SyncLogFactory):
    """Factory for download-only sync logs."""

    direction = SyncLog.Direction.DOWNLOAD


class SyncConflictFactory(DjangoModelFactory):
    """Factory for SyncConflict model."""

    class Meta:
        model = SyncConflict

    sync_log = factory.SubFactory(InProgressSyncLogFactory)
    model_name = factory.Sequence(lambda n: f"TestModel{n % 5}")
    record_id = factory.Sequence(lambda n: str(n))
    server_data = factory.LazyFunction(
        lambda: {"title": "Server Value", "updated_at": timezone.now().isoformat()}
    )
    client_data = factory.LazyFunction(
        lambda: {"title": "Client Value", "updated_at": timezone.now().isoformat()}
    )
    resolution = SyncConflict.Resolution.PENDING
    resolved_data = None
    resolved_by = None
    resolved_at = None


class PendingConflictFactory(SyncConflictFactory):
    """Factory for pending conflicts."""

    resolution = SyncConflict.Resolution.PENDING
    resolved_data = None
    resolved_by = None
    resolved_at = None


class ServerWinsConflictFactory(SyncConflictFactory):
    """Factory for server-wins resolved conflicts."""

    resolution = SyncConflict.Resolution.SERVER_WINS
    resolved_data = factory.LazyAttribute(lambda obj: obj.server_data)
    resolved_by = factory.SubFactory(UserFactory)
    resolved_at = factory.LazyFunction(timezone.now)


class ClientWinsConflictFactory(SyncConflictFactory):
    """Factory for client-wins resolved conflicts."""

    resolution = SyncConflict.Resolution.CLIENT_WINS
    resolved_data = factory.LazyAttribute(lambda obj: obj.client_data)
    resolved_by = factory.SubFactory(UserFactory)
    resolved_at = factory.LazyFunction(timezone.now)


class MergedConflictFactory(SyncConflictFactory):
    """Factory for merged resolved conflicts."""

    resolution = SyncConflict.Resolution.MERGED
    resolved_data = factory.LazyFunction(
        lambda: {
            "title": "Merged Value",
            "updated_at": timezone.now().isoformat(),
            "merged": True,
        }
    )
    resolved_by = factory.SubFactory(UserFactory)
    resolved_at = factory.LazyFunction(timezone.now)


class ManualConflictFactory(SyncConflictFactory):
    """Factory for manually resolved conflicts."""

    resolution = SyncConflict.Resolution.MANUAL
    resolved_data = factory.LazyFunction(
        lambda: {"title": "Manual Value", "manually_resolved": True}
    )
    resolved_by = factory.SubFactory(UserFactory)
    resolved_at = factory.LazyFunction(timezone.now)


class OfflinePackageFactory(DjangoModelFactory):
    """Factory for OfflinePackage model."""

    class Meta:
        model = OfflinePackage

    name = factory.Sequence(lambda n: f"Offline Package {n}")
    description = factory.Faker("paragraph")
    course = factory.SubFactory(CourseFactory)
    version = 1
    status = OfflinePackage.Status.READY
    package_file = None
    file_size = factory.Faker("random_int", min=1024, max=104857600)
    checksum = factory.Sequence(lambda n: f"sha256:{n:064d}")
    includes_videos = True
    includes_documents = True
    includes_assessments = True
    manifest = factory.LazyFunction(
        lambda: {
            "modules": [],
            "lessons": [],
            "resources": [],
            "total_items": 0,
        }
    )
    build_started_at = None
    build_completed_at = None
    error_message = ""


class BuildingPackageFactory(OfflinePackageFactory):
    """Factory for packages currently being built."""

    status = OfflinePackage.Status.BUILDING
    build_started_at = factory.LazyFunction(timezone.now)
    build_completed_at = None
    package_file = None
    file_size = None
    checksum = ""


class ReadyPackageFactory(OfflinePackageFactory):
    """Factory for ready packages."""

    status = OfflinePackage.Status.READY
    build_started_at = factory.LazyFunction(lambda: timezone.now() - timedelta(hours=1))
    build_completed_at = factory.LazyFunction(timezone.now)

    @factory.lazy_attribute
    def package_file(self):
        """Generate a fake package file."""
        content = b"PK\x03\x04" + b"\x00" * 100  # Fake ZIP header
        return ContentFile(content, name=f"package_{self.course.code}_v{self.version}.zip")


class OutdatedPackageFactory(OfflinePackageFactory):
    """Factory for outdated packages."""

    status = OfflinePackage.Status.OUTDATED
    build_started_at = factory.LazyFunction(lambda: timezone.now() - timedelta(days=30))
    build_completed_at = factory.LazyFunction(lambda: timezone.now() - timedelta(days=30))


class ErrorPackageFactory(OfflinePackageFactory):
    """Factory for packages with build errors."""

    status = OfflinePackage.Status.ERROR
    build_started_at = factory.LazyFunction(lambda: timezone.now() - timedelta(hours=1))
    build_completed_at = None
    error_message = "Build failed: Insufficient disk space"
    package_file = None
    file_size = None
    checksum = ""


class PackageDownloadFactory(DjangoModelFactory):
    """Factory for PackageDownload model."""

    class Meta:
        model = PackageDownload

    package = factory.SubFactory(ReadyPackageFactory)
    user = factory.SubFactory(UserFactory)
    device_id = factory.Sequence(lambda n: f"download-device-{n:06d}")
    download_completed = False
    last_accessed_at = None


class CompletedDownloadFactory(PackageDownloadFactory):
    """Factory for completed downloads."""

    download_completed = True
    last_accessed_at = factory.LazyFunction(timezone.now)


class InProgressDownloadFactory(PackageDownloadFactory):
    """Factory for in-progress downloads."""

    download_completed = False
    last_accessed_at = None


# Trait-based factory for complex scenarios
class SyncLogWithConflictsFactory(SyncLogFactory):
    """Factory for sync logs with associated conflicts."""

    status = SyncLog.Status.PARTIAL

    @factory.post_generation
    def conflicts(self, create, extracted, **kwargs):
        if not create:
            return

        if extracted:
            for conflict_data in extracted:
                SyncConflictFactory(sync_log=self, **conflict_data)
        else:
            # Create 3 default conflicts
            for i in range(3):
                SyncConflictFactory(
                    sync_log=self,
                    model_name=f"Model{i}",
                    record_id=str(i + 1),
                )


class OfflinePackageWithDownloadsFactory(OfflinePackageFactory):
    """Factory for packages with associated downloads."""

    status = OfflinePackage.Status.READY

    @factory.post_generation
    def downloads(self, create, extracted, **kwargs):
        if not create:
            return

        if extracted:
            for download_data in extracted:
                PackageDownloadFactory(package=self, **download_data)
        else:
            # Create 5 default downloads
            for i in range(5):
                PackageDownloadFactory(
                    package=self,
                    download_completed=(i % 2 == 0),
                )


# Batch factories for performance testing
class SyncLogBatchFactory:
    """Helper factory for creating batches of sync logs."""

    @staticmethod
    def create_batch_for_user(user, count=10, **kwargs):
        """Create multiple sync logs for a specific user."""
        return SyncLogFactory.create_batch(count, user=user, **kwargs)

    @staticmethod
    def create_mixed_status_batch(user, count=10):
        """Create sync logs with various statuses."""
        factories = [
            PendingSyncLogFactory,
            InProgressSyncLogFactory,
            CompletedSyncLogFactory,
            FailedSyncLogFactory,
            PartialSyncLogFactory,
        ]
        logs = []
        for i in range(count):
            factory_class = factories[i % len(factories)]
            logs.append(factory_class(user=user))
        return logs


class ConflictBatchFactory:
    """Helper factory for creating batches of conflicts."""

    @staticmethod
    def create_batch_for_sync_log(sync_log, count=5, **kwargs):
        """Create multiple conflicts for a specific sync log."""
        return SyncConflictFactory.create_batch(count, sync_log=sync_log, **kwargs)

    @staticmethod
    def create_for_multiple_models(sync_log, models):
        """Create conflicts for different model types."""
        conflicts = []
        for model_name in models:
            conflicts.append(
                SyncConflictFactory(
                    sync_log=sync_log,
                    model_name=model_name,
                    record_id="1",
                )
            )
        return conflicts
