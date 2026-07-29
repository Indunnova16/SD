"""
Celery tasks for course content processing.
"""

import logging
import os
import subprocess
import tempfile
from pathlib import Path

from django.core.files.base import ContentFile
from django.utils import timezone

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def process_media_asset(self, asset_id: int):
    """
    Process uploaded media asset (video transcoding, thumbnail generation, etc).
    """
    from apps.courses.models import MediaAsset

    try:
        asset = MediaAsset.objects.get(id=asset_id)
    except MediaAsset.DoesNotExist:
        logger.error(f"MediaAsset {asset_id} not found")
        return

    asset.status = MediaAsset.Status.PROCESSING
    asset.save()

    try:
        if asset.file_type == MediaAsset.Type.VIDEO:
            _process_video(asset)
        elif asset.file_type == MediaAsset.Type.AUDIO:
            _process_audio(asset)
        elif asset.file_type == MediaAsset.Type.IMAGE:
            _process_image(asset)
        elif asset.file_type == MediaAsset.Type.DOCUMENT:
            _process_document(asset)
        elif asset.file_type == MediaAsset.Type.SCORM:
            _process_scorm_package(asset)

        asset.status = MediaAsset.Status.READY
        asset.save()

        logger.info(f"MediaAsset {asset_id} processed successfully")

    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.error(f"Error de procesamiento multimedia para asset {asset_id}: {e}")
        asset.status = MediaAsset.Status.ERROR
        asset.processing_error = f"Error de procesamiento: {e}"
        asset.save()
        # Retry con backoff exponencial
        raise self.retry(exc=e, countdown=60 * (2**self.request.retries))
    except OSError as e:
        logger.error(f"Error de I/O para asset {asset_id}: {e}")
        asset.status = MediaAsset.Status.ERROR
        asset.processing_error = f"Error de archivo: {e}"
        asset.save()
        raise self.retry(exc=e, countdown=60 * (2**self.request.retries))
    except Exception as e:
        logger.exception(f"Error inesperado procesando MediaAsset {asset_id}: {e}")
        asset.status = MediaAsset.Status.ERROR
        asset.processing_error = "Error inesperado durante el procesamiento."
        asset.save()
        # Retry con backoff exponencial
        raise self.retry(exc=e, countdown=60 * (2**self.request.retries))


def _process_video(asset):
    """Process video file: extract duration, generate thumbnail, create compressed version."""

    file_path = asset.file.path

    # Get video duration and metadata using ffprobe
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0 and result.stdout.strip():
            asset.duration = int(float(result.stdout.strip()))
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.warning(f"Could not get video duration: {e}")
        asset.duration = 0

    # Generate thumbnail at 10% of video duration
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as thumb_file:
            thumb_path = thumb_file.name

        seek_time = max(1, (asset.duration or 0) // 10)

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                str(seek_time),
                "-i",
                file_path,
                "-vframes",
                "1",
                "-vf",
                "scale=320:-1",
                thumb_path,
            ],
            capture_output=True,
            timeout=120,
        )

        if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 0:
            with open(thumb_path, "rb") as f:
                thumb_name = f"thumb_{asset.filename}.jpg"
                asset.thumbnail.save(thumb_name, ContentFile(f.read()), save=False)

            os.unlink(thumb_path)

    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.warning(f"Could not generate thumbnail: {e}")

    # Create compressed version for offline use
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as compressed_file:
            compressed_path = compressed_file.name

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                file_path,
                "-c:v",
                "libx264",
                "-crf",
                "28",  # Higher CRF = more compression
                "-preset",
                "medium",
                "-c:a",
                "aac",
                "-b:a",
                "64k",
                "-vf",
                "scale=720:-2",  # 720p max
                compressed_path,
            ],
            capture_output=True,
            timeout=3600,  # 1 hour max for large videos
        )

        if os.path.exists(compressed_path) and os.path.getsize(compressed_path) > 0:
            with open(compressed_path, "rb") as f:
                compressed_name = f"offline_{asset.filename}"
                asset.compressed_file.save(compressed_name, ContentFile(f.read()), save=False)

            os.unlink(compressed_path)

    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.warning(f"Could not create compressed version: {e}")

    # Extract metadata
    asset.metadata = {
        "processed_at": timezone.now().isoformat(),
        "original_size": asset.size,
        "compressed_size": asset.compressed_file.size if asset.compressed_file else None,
    }


def _process_audio(asset):
    """Process audio file: extract duration, create compressed version."""
    file_path = asset.file.path

    # Get audio duration
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0 and result.stdout.strip():
            asset.duration = int(float(result.stdout.strip()))
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.warning(f"Could not get audio duration: {e}")

    # Create compressed version
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as compressed_file:
            compressed_path = compressed_file.name

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                file_path,
                "-c:a",
                "libmp3lame",
                "-b:a",
                "64k",
                compressed_path,
            ],
            capture_output=True,
            timeout=600,
        )

        if os.path.exists(compressed_path) and os.path.getsize(compressed_path) > 0:
            with open(compressed_path, "rb") as f:
                compressed_name = f"offline_{asset.filename}.mp3"
                asset.compressed_file.save(compressed_name, ContentFile(f.read()), save=False)

            os.unlink(compressed_path)

    except (subprocess.SubprocessError, FileNotFoundError) as e:
        logger.warning(f"Could not create compressed audio: {e}")


def _process_image(asset):
    """Process image: generate thumbnail, optimize for web."""
    from PIL import Image

    file_path = asset.file.path

    try:
        with Image.open(file_path) as img:
            # Store original dimensions
            asset.metadata = {
                "width": img.width,
                "height": img.height,
                "format": img.format,
            }

            # Generate thumbnail
            thumb_size = (320, 320)
            thumb = img.copy()
            thumb.thumbnail(thumb_size, Image.Resampling.LANCZOS)

            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as thumb_file:
                thumb_path = thumb_file.name
                if img.mode in ("RGBA", "P"):
                    thumb = thumb.convert("RGB")
                thumb.save(thumb_path, "JPEG", quality=85)

            with open(thumb_path, "rb") as f:
                thumb_name = f"thumb_{asset.filename}.jpg"
                asset.thumbnail.save(thumb_name, ContentFile(f.read()), save=False)

            os.unlink(thumb_path)

    except OSError as e:
        logger.warning(f"Error de I/O procesando imagen {asset.id}: {e}")
    except ImportError:
        logger.warning("PIL/Pillow no esta instalado, saltando procesamiento de imagen")
    except Exception as e:
        logger.exception(f"Error inesperado procesando imagen {asset.id}: {e}")


def _process_document(asset):
    """Process document: extract metadata, generate preview if PDF."""
    file_path = asset.file.path

    # Basic metadata
    asset.metadata = {
        "extension": Path(file_path).suffix.lower(),
        "processed_at": timezone.now().isoformat(),
    }

    # Generate PDF thumbnail if it's a PDF
    if asset.mime_type == "application/pdf":
        try:
            from pdf2image import convert_from_path

            pages = convert_from_path(file_path, first_page=1, last_page=1, dpi=72)
            if pages:
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as thumb_file:
                    thumb_path = thumb_file.name
                    pages[0].save(thumb_path, "JPEG")

                with open(thumb_path, "rb") as f:
                    thumb_name = f"thumb_{asset.filename}.jpg"
                    asset.thumbnail.save(thumb_name, ContentFile(f.read()), save=False)

                os.unlink(thumb_path)

        except ImportError:
            logger.warning("pdf2image no esta instalado, saltando generacion de thumbnail PDF")
        except OSError as e:
            logger.warning(f"Error de I/O generando thumbnail PDF para asset {asset.id}: {e}")
        except Exception as e:
            logger.exception(f"Error inesperado generando thumbnail PDF para asset {asset.id}: {e}")


def _process_scorm_package(asset):
    """Process SCORM package: validate and extract manifest."""
    import zipfile

    file_path = asset.file.path

    try:
        with zipfile.ZipFile(file_path, "r") as zip_ref:
            # Check for SCORM manifest
            manifest_name = None
            for name in ["imsmanifest.xml", "tincan.xml"]:
                if name in zip_ref.namelist():
                    manifest_name = name
                    break

            if not manifest_name:
                raise ValueError("No SCORM manifest found in package")

            # Extract manifest content
            manifest_content = zip_ref.read(manifest_name).decode("utf-8")

            # Basic validation - check for required elements
            if "imsmanifest.xml" in manifest_name:
                # SCORM 1.2 or 2004
                scorm_version = "SCORM 2004" if "adlcp:" in manifest_content else "SCORM 1.2"
            else:
                scorm_version = "xAPI/TinCan"

            # Get file list
            file_list = zip_ref.namelist()

            asset.metadata = {
                "scorm_version": scorm_version,
                "manifest_file": manifest_name,
                "file_count": len(file_list),
                "processed_at": timezone.now().isoformat(),
            }

    except zipfile.BadZipFile:
        raise ValueError("Invalid ZIP file")


@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def generate_course_package(self, course_id: int, include_videos: bool = True):
    """
    Generate offline package for a course.
    """
    from apps.courses.models import Course
    from apps.sync.models import OfflinePackage

    try:
        course = Course.objects.prefetch_related("modules__lessons").get(id=course_id)
    except Course.DoesNotExist:
        logger.error(f"Course {course_id} not found")
        return

    # Create or update offline package
    package, created = OfflinePackage.objects.get_or_create(
        course=course,
        defaults={
            "name": f"Paquete Offline - {course.title}",
            "includes_videos": include_videos,
            "includes_documents": True,
            "includes_assessments": True,
            "status": OfflinePackage.Status.BUILDING,
        },
    )

    if not created:
        package.version += 1
        package.status = OfflinePackage.Status.BUILDING
        package.build_started_at = timezone.now()
        package.save()

    try:
        # Generate package (simplified - would create actual ZIP in production)
        manifest = {
            "course_id": course.id,
            "course_code": course.code,
            "title": course.title,
            "version": package.version,
            "modules": [],
        }

        for module in course.modules.all():
            module_data = {
                "id": module.id,
                "title": module.title,
                "lessons": [],
            }

            for lesson in module.lessons.all():
                lesson_data = {
                    "id": lesson.id,
                    "title": lesson.title,
                    "type": lesson.lesson_type,
                    "duration": lesson.duration,
                }
                module_data["lessons"].append(lesson_data)

            manifest["modules"].append(module_data)

        package.manifest = manifest
        package.status = OfflinePackage.Status.READY
        package.build_completed_at = timezone.now()
        package.save()

        logger.info(f"Course package for {course_id} generated successfully")

    except OSError as e:
        logger.error(f"Error de I/O generando paquete para curso {course_id}: {e}")
        package.status = OfflinePackage.Status.ERROR
        package.error_message = f"Error de sistema de archivos: {e}"
        package.save()
        raise self.retry(exc=e, countdown=120 * (2**self.request.retries))
    except Exception as e:
        logger.exception(f"Error inesperado generando paquete para curso {course_id}: {e}")
        package.status = OfflinePackage.Status.ERROR
        package.error_message = "Error inesperado durante la generacion."
        package.save()
        # Solo reintentar si no hemos alcanzado el maximo
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=120 * (2**self.request.retries))


@shared_task
def cleanup_expired_assets():
    """Clean up temporary or expired media assets."""
    from apps.courses.models import MediaAsset

    # Delete assets in error state older than 7 days
    cutoff = timezone.now() - timezone.timedelta(days=7)
    expired = MediaAsset.objects.filter(
        status=MediaAsset.Status.ERROR,
        created_at__lt=cutoff,
    )

    count = expired.count()
    for asset in expired:
        try:
            if asset.file:
                asset.file.delete(save=False)
            if asset.thumbnail:
                asset.thumbnail.delete(save=False)
            if asset.compressed_file:
                asset.compressed_file.delete(save=False)
            asset.delete()
        except Exception as e:
            logger.error(f"Error cleaning up asset {asset.id}: {e}")

    logger.info(f"Cleaned up {count} expired media assets")


@shared_task
def calculate_course_statistics(course_id: int):
    """Calculate and cache course statistics."""
    from django.db.models import Avg, Sum

    from apps.courses.models import Course, Enrollment, LessonProgress

    try:
        course = Course.objects.get(id=course_id)
    except Course.DoesNotExist:
        return

    enrollments = Enrollment.objects.filter(course=course)

    stats = {
        "total_enrollments": enrollments.count(),
        "completed": enrollments.filter(status=Enrollment.Status.COMPLETED).count(),
        "in_progress": enrollments.filter(status=Enrollment.Status.IN_PROGRESS).count(),
        "average_progress": enrollments.aggregate(avg=Avg("progress"))["avg"] or 0,
        "total_time_spent": LessonProgress.objects.filter(enrollment__course=course).aggregate(
            total=Sum("time_spent")
        )["total"]
        or 0,
    }

    # Calculate completion rate
    if stats["total_enrollments"] > 0:
        stats["completion_rate"] = (stats["completed"] / stats["total_enrollments"]) * 100
    else:
        stats["completion_rate"] = 0

    # Store in course metadata or cache
    from django.core.cache import cache

    cache.set(f"course_stats_{course_id}", stats, timeout=3600)

    return stats


@shared_task
def check_enrollment_deadlines():
    """
    Check enrollment deadlines daily:
    - Mark overdue enrollments as expired
    - Send notifications to users and admins
    - Alert for enrollments expiring in 1 or 3 days
    """
    from django.contrib.auth import get_user_model

    from apps.courses.models import Enrollment

    User = get_user_model()
    today = timezone.now().date()
    admin_users = User.objects.filter(is_staff=True, is_active=True)

    # 1. Mark overdue enrollments as expired
    overdue = Enrollment.objects.filter(
        due_date__lt=today,
        status__in=[Enrollment.Status.ENROLLED, Enrollment.Status.IN_PROGRESS],
    ).select_related("user", "course")

    for enrollment in overdue:
        enrollment.status = Enrollment.Status.EXPIRED
        enrollment.save(update_fields=["status", "updated_at"])

        # Notify user
        _send_deadline_notification(
            user=enrollment.user,
            title="Curso vencido",
            message=f"Tu curso '{enrollment.course.title}' ha vencido. Puedes habilitarlo de nuevo desde Mis Cursos.",
            priority="high",
        )

        # Notify admins
        for admin in admin_users:
            _send_deadline_notification(
                user=admin,
                title="Curso vencido - Usuario",
                message=(
                    f"El curso '{enrollment.course.title}' del usuario "
                    f"{enrollment.user.get_full_name()} ({enrollment.user.document_number}) ha vencido."
                ),
                priority="normal",
            )

    if overdue.exists():
        logger.info(f"Marked {overdue.count()} enrollment(s) as expired")

    # 2. Alert for enrollments expiring soon (3 days and 1 day)
    for days_left in [3, 1]:
        target_date = today + timezone.timedelta(days=days_left)
        expiring = Enrollment.objects.filter(
            due_date=target_date,
            status__in=[Enrollment.Status.ENROLLED, Enrollment.Status.IN_PROGRESS],
        ).select_related("user", "course")

        for enrollment in expiring:
            priority = "urgent" if days_left == 1 else "high"
            _send_deadline_notification(
                user=enrollment.user,
                title=f"Curso por vencer en {days_left} día{'s' if days_left > 1 else ''}",
                message=(
                    f"Tu curso '{enrollment.course.title}' vence el "
                    f"{enrollment.due_date.strftime('%d/%m/%Y')}. "
                    f"Quedan {days_left} día{'s' if days_left > 1 else ''}."
                ),
                priority=priority,
            )

        if expiring.exists():
            logger.info(
                f"Sent {expiring.count()} reminder(s) for enrollments expiring in {days_left} day(s)"
            )


def _send_deadline_notification(user, title, message, priority="normal"):
    """
    Helper to create in-app notification for deadline alerts.

    Delega en NotificationService (la API que usa el resto del codigo) en vez de
    construir el modelo a mano: el modelo expone `subject`/`body`, no
    `title`/`message`, y construirlo directo hace que cualquier desalineacion de
    nombres solo explote en runtime. Ver SD#75.
    """
    try:
        from apps.notifications.models import NotificationTemplate
        from apps.notifications.services import NotificationService

        notification = NotificationService.create_notification(
            user=user,
            subject=title,
            body=message,
            channel=NotificationTemplate.Channel.IN_APP,
            priority=priority,
        )
        # Las alertas de vencimiento son in-app puras: quedan disponibles al
        # usuario apenas se crean, sin pasar por un canal externo.
        NotificationService.mark_as_delivered(notification)
        return notification
    except Exception as e:
        # NO degradar a warning sin traza: un `except` que descarta el stack
        # convirtio el typo de SD#75 en un fallo invisible durante meses.
        logger.exception(f"Error inesperado creando notificacion de vencimiento para {user}: {e}")
        return None
