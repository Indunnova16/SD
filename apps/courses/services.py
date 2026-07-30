"""
Business logic services for course management.
"""

import logging
import mimetypes
import os
import uuid
import zipfile
from pathlib import Path

from django.conf import settings
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone

from apps.courses.models import (
    Course,
    CourseSchedule,
    CourseVersion,
    Enrollment,
    Lesson,
    LessonProgress,
    MediaAsset,
    Module,
    ResourceLibrary,
    ScheduleAssignment,
    ScormPackage,
)

logger = logging.getLogger(__name__)


class CourseService:
    """Service for course management operations."""

    @staticmethod
    @transaction.atomic
    def create_course(data: dict, user) -> Course:
        """Create a new course with optional modules and lessons."""
        modules_data = data.pop("modules", [])

        course = Course.objects.create(
            created_by=user,
            **data,
        )

        for order, module_data in enumerate(modules_data):
            lessons_data = module_data.pop("lessons", [])
            module = Module.objects.create(
                course=course,
                order=order,
                **module_data,
            )
            for lesson_order, lesson_data in enumerate(lessons_data):
                Lesson.objects.create(
                    module=module,
                    order=lesson_order,
                    **lesson_data,
                )

        return course

    @staticmethod
    @transaction.atomic
    def publish_course(course: Course, user, changelog: str = "") -> Course:
        """Publish a course and create a version snapshot."""
        if course.status == Course.Status.PUBLISHED:
            raise ValueError("El curso ya está publicado")

        # Create version snapshot before publishing
        CourseVersion.create_snapshot(
            course=course,
            user=user,
            changelog=changelog or "Publicación inicial",
            is_major=True,
        )

        course.status = Course.Status.PUBLISHED
        course.published_at = timezone.now()
        course.version += 1
        course.save()

        return course

    @staticmethod
    @transaction.atomic
    def archive_course(course: Course, user) -> Course:
        """Archive a course."""
        if course.status == Course.Status.ARCHIVED:
            raise ValueError("El curso ya está archivado")

        # Create version snapshot before archiving
        CourseVersion.create_snapshot(
            course=course,
            user=user,
            changelog="Curso archivado",
        )

        course.status = Course.Status.ARCHIVED
        course.save()

        return course

    @staticmethod
    @transaction.atomic
    def duplicate_course(course: Course, user, new_code: str = None) -> Course:
        """Create a copy of a course with all its content."""
        # Generate new code if not provided
        if not new_code:
            new_code = f"{course.code}-COPY-{uuid.uuid4().hex[:6].upper()}"

        # Clone course
        new_course = Course.objects.create(
            code=new_code,
            title=f"{course.title} (Copia)",
            description=course.description,
            objectives=course.objectives,
            course_type=course.course_type,
            target_profiles=course.target_profiles,
            validity_months=course.validity_months,
            category=course.category,
            status=Course.Status.DRAFT,
            created_by=user,
        )

        # Clone modules and lessons - use prefetch_related to avoid N+1 queries
        for module in course.modules.prefetch_related("lessons").all():
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
                    content_file=lesson.content_file,
                    video_url=lesson.video_url,
                    duration=lesson.duration,
                    order=lesson.order,
                    is_mandatory=lesson.is_mandatory,
                    is_offline_available=lesson.is_offline_available,
                    metadata=lesson.metadata,
                )

        return new_course

    @staticmethod
    def calculate_course_duration(course: Course) -> int:
        """Calculate total course duration from lessons."""
        total = 0
        for module in course.modules.prefetch_related("lessons").all():
            total += sum(lesson.duration for lesson in module.lessons.all())
        return total

    @staticmethod
    def get_course_statistics(course: Course) -> dict:
        """Get course statistics."""
        from django.db.models import Avg

        enrollments = Enrollment.objects.filter(course=course)

        stats = {
            "total_enrollments": enrollments.count(),
            "completed": enrollments.filter(status=Enrollment.Status.COMPLETED).count(),
            "in_progress": enrollments.filter(status=Enrollment.Status.IN_PROGRESS).count(),
            "enrolled": enrollments.filter(status=Enrollment.Status.ENROLLED).count(),
            "expired": enrollments.filter(status=Enrollment.Status.EXPIRED).count(),
            "average_progress": enrollments.aggregate(avg=Avg("progress"))["avg"] or 0,
            "module_count": course.modules.count(),
            "lesson_count": Lesson.objects.filter(module__course=course).count(),
        }

        if stats["total_enrollments"] > 0:
            stats["completion_rate"] = round(
                (stats["completed"] / stats["total_enrollments"]) * 100, 2
            )
        else:
            stats["completion_rate"] = 0

        return stats


class EnrollmentService:
    """Service for enrollment management."""

    @staticmethod
    @transaction.atomic
    def enroll_user(user, course: Course, assigned_by=None, due_date=None) -> Enrollment:
        """Enroll a user in a course."""
        # Check prerequisites
        if course.prerequisites.exists():
            completed_prereqs = Enrollment.objects.filter(
                user=user,
                course__in=course.prerequisites.all(),
                status=Enrollment.Status.COMPLETED,
            ).count()

            if completed_prereqs < course.prerequisites.count():
                raise ValueError("No ha completado los prerrequisitos del curso")

        enrollment, created = Enrollment.objects.get_or_create(
            user=user,
            course=course,
            defaults={
                "assigned_by": assigned_by,
                "due_date": due_date,
                "status": Enrollment.Status.ENROLLED,
            },
        )

        if not created and enrollment.status == Enrollment.Status.EXPIRED:
            # Re-enroll if expired
            enrollment.status = Enrollment.Status.ENROLLED
            enrollment.due_date = due_date
            enrollment.assigned_by = assigned_by
            enrollment.progress = 0
            enrollment.started_at = None
            enrollment.completed_at = None
            enrollment.save()

        return enrollment

    @staticmethod
    @transaction.atomic
    def update_progress(
        enrollment: Enrollment, lesson: Lesson, progress_data: dict
    ) -> LessonProgress:
        """Update user progress for a lesson."""
        lesson_progress, _ = LessonProgress.objects.get_or_create(
            enrollment=enrollment,
            lesson=lesson,
        )

        # Update progress fields
        if "progress_percent" in progress_data:
            lesson_progress.progress_percent = progress_data["progress_percent"]

        if "time_spent" in progress_data:
            lesson_progress.time_spent += progress_data.get("time_spent", 0)

        if "last_position" in progress_data:
            lesson_progress.last_position = progress_data["last_position"]

        if progress_data.get("completed", False) or lesson_progress.progress_percent >= 100:
            lesson_progress.is_completed = True
            lesson_progress.completed_at = timezone.now()

        lesson_progress.save()

        # Update enrollment progress
        EnrollmentService._update_enrollment_progress(enrollment)

        return lesson_progress

    @staticmethod
    def update_enrollment_progress(enrollment: Enrollment) -> Enrollment:
        """
        Recalculate enrollment progress based on lesson completion.

        This method calculates the overall progress of an enrollment based on
        completed mandatory lessons and updates the enrollment status accordingly.

        Args:
            enrollment: The Enrollment instance to update.

        Returns:
            The updated Enrollment instance.
        """
        total_lessons = Lesson.objects.filter(
            module__course=enrollment.course,
            is_mandatory=True,
        ).count()

        if total_lessons == 0:
            return enrollment

        completed_lessons = LessonProgress.objects.filter(
            enrollment=enrollment,
            lesson__is_mandatory=True,
            is_completed=True,
        ).count()

        progress = (completed_lessons / total_lessons) * 100
        enrollment.progress = round(progress, 2)

        if enrollment.progress > 0 and enrollment.status == Enrollment.Status.ENROLLED:
            enrollment.status = Enrollment.Status.IN_PROGRESS
            enrollment.started_at = timezone.now()

        if progress >= 100:
            enrollment.status = Enrollment.Status.COMPLETED
            enrollment.completed_at = timezone.now()

        enrollment.save()
        return enrollment

    # Alias for backward compatibility
    _update_enrollment_progress = update_enrollment_progress

    @staticmethod
    def is_lesson_accessible(enrollment, lesson):
        """
        Check if a lesson is accessible based on sequential completion.
        A lesson is accessible if it's the first lesson or all previous
        mandatory lessons are completed.
        Returns: (is_accessible, blocking_lesson or None)
        """
        all_lessons = list(
            Lesson.objects.filter(module__course=enrollment.course).order_by(
                "module__order", "order"
            )
        )

        lesson_index = None
        for i, current_lesson in enumerate(all_lessons):
            if current_lesson.id == lesson.id:
                lesson_index = i
                break

        if lesson_index is None:
            return False, None

        if lesson_index == 0:
            return True, None

        completed_ids = set(
            LessonProgress.objects.filter(
                enrollment=enrollment,
                is_completed=True,
            ).values_list("lesson_id", flat=True)
        )

        for prev_lesson in all_lessons[:lesson_index]:
            if prev_lesson.is_mandatory and prev_lesson.id not in completed_ids:
                return False, prev_lesson

        return True, None

    @staticmethod
    def get_next_lesson_context(enrollment, lesson):
        """
        Resolve the lesson that follows ``lesson`` (in course module/lesson
        order) for ``enrollment``, plus whether it is currently accessible.

        Extracted (SD#54, reproceso 3ra ronda) from the inline logic in
        ``apps.courses.views.lesson_view`` so it can be reused by
        ``apps.assessments.views.attempt_result`` -- the "aprobado" branch of
        the assessment result screen needs the exact same next-lesson lookup
        to offer a "Continuar Curso" action, and duplicating it a third time
        was flagged as the risk to avoid in the fix plan.

        Returns: (next_lesson or None, next_lesson_accessible: bool)
        """
        all_lessons = list(
            Lesson.objects.filter(module__course=enrollment.course).order_by(
                "module__order", "order"
            )
        )

        current_index = None
        for i, current_lesson in enumerate(all_lessons):
            if current_lesson.id == lesson.id:
                current_index = i
                break

        if current_index is None:
            return None, False

        next_lesson = (
            all_lessons[current_index + 1] if current_index < len(all_lessons) - 1 else None
        )

        next_lesson_accessible = True
        if next_lesson:
            next_lesson_accessible, _ = EnrollmentService.is_lesson_accessible(
                enrollment, next_lesson
            )

        return next_lesson, next_lesson_accessible

    @staticmethod
    def get_lesson_accessibility_map(enrollment):
        """
        Get a dict mapping lesson_id -> {is_accessible, is_completed}
        for all lessons in the course. Used for rendering locked/unlocked states.
        """
        all_lessons = list(
            Lesson.objects.filter(module__course=enrollment.course).order_by(
                "module__order", "order"
            )
        )

        completed_ids = set(
            LessonProgress.objects.filter(
                enrollment=enrollment,
                is_completed=True,
            ).values_list("lesson_id", flat=True)
        )

        accessibility = {}
        all_previous_mandatory_done = True

        for lesson in all_lessons:
            is_completed = lesson.id in completed_ids
            accessibility[lesson.id] = {
                "is_accessible": all_previous_mandatory_done,
                "is_completed": is_completed,
            }
            if lesson.is_mandatory and not is_completed:
                all_previous_mandatory_done = False

        return accessibility


class MediaService:
    """Service for media asset management."""

    ALLOWED_VIDEO_TYPES = ["video/mp4", "video/webm", "video/quicktime"]
    ALLOWED_AUDIO_TYPES = ["audio/mpeg", "audio/wav", "audio/ogg"]
    ALLOWED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/gif", "image/webp"]
    ALLOWED_DOCUMENT_TYPES = [
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ]

    @staticmethod
    def upload_asset(file, user, file_type: str = None) -> MediaAsset:
        """Upload a media asset and queue for processing."""
        from apps.courses.tasks import process_media_asset

        # Determine file type
        mime_type, _ = mimetypes.guess_type(file.name)
        mime_type = mime_type or "application/octet-stream"

        if not file_type:
            if mime_type in MediaService.ALLOWED_VIDEO_TYPES:
                file_type = MediaAsset.Type.VIDEO
            elif mime_type in MediaService.ALLOWED_AUDIO_TYPES:
                file_type = MediaAsset.Type.AUDIO
            elif mime_type in MediaService.ALLOWED_IMAGE_TYPES:
                file_type = MediaAsset.Type.IMAGE
            elif mime_type in MediaService.ALLOWED_DOCUMENT_TYPES:
                file_type = MediaAsset.Type.DOCUMENT
            elif mime_type == "application/zip":
                file_type = MediaAsset.Type.SCORM
            else:
                file_type = MediaAsset.Type.DOCUMENT

        # Generate unique filename
        ext = Path(file.name).suffix
        filename = f"{uuid.uuid4().hex}{ext}"

        asset = MediaAsset.objects.create(
            filename=filename,
            original_name=file.name,
            file=file,
            file_type=file_type,
            mime_type=mime_type,
            size=file.size,
            status=MediaAsset.Status.PENDING,
            uploaded_by=user,
        )

        # Queue for processing
        process_media_asset.delay(asset.id)

        return asset

    @staticmethod
    def get_asset_status(asset_id: int) -> dict:
        """Get current processing status of an asset."""
        try:
            asset = MediaAsset.objects.get(id=asset_id)
            return {
                "id": asset.id,
                "status": asset.status,
                "error": asset.processing_error,
                "thumbnail_url": asset.thumbnail.url if asset.thumbnail else None,
                "compressed_url": asset.compressed_file.url if asset.compressed_file else None,
            }
        except MediaAsset.DoesNotExist:
            return {"error": "Asset not found"}


class ScormService:
    """Service for SCORM package management."""

    @staticmethod
    @transaction.atomic
    def process_package(scorm_package: ScormPackage) -> ScormPackage:
        """Extract and validate a SCORM package."""
        import xml.etree.ElementTree as ET

        scorm_package.status = ScormPackage.Status.EXTRACTING
        scorm_package.save()

        try:
            file_path = scorm_package.package_file.path

            # Validate ZIP file
            if not zipfile.is_zipfile(file_path):
                raise ValueError("El archivo no es un ZIP válido")

            # Create extraction directory
            extract_dir = os.path.join(
                settings.MEDIA_ROOT,
                "scorm_content",
                str(scorm_package.lesson.module.course.id),
                str(scorm_package.id),
            )
            os.makedirs(extract_dir, exist_ok=True)

            with zipfile.ZipFile(file_path, "r") as zip_ref:
                # Check for manifest
                manifest_name = None
                for name in zip_ref.namelist():
                    if name.lower() == "imsmanifest.xml":
                        manifest_name = name
                        break

                if not manifest_name:
                    raise ValueError("No se encontró el manifiesto SCORM (imsmanifest.xml)")

                # Extract all files
                zip_ref.extractall(extract_dir)

                # Parse manifest
                manifest_path = os.path.join(extract_dir, manifest_name)
                tree = ET.parse(manifest_path)
                root = tree.getroot()

                # Determine SCORM version
                namespaces = {
                    "adlcp": "http://www.adlnet.org/xsd/adlcp_rootv1p2",
                    "imscp": "http://www.imsglobal.org/xsd/imscp_v1p1",
                }

                if "adlcp" in root.tag or any("adlcp" in str(root.attrib.values()) for _ in [1]):
                    scorm_package.scorm_version = ScormPackage.Version.SCORM_2004
                else:
                    scorm_package.scorm_version = ScormPackage.Version.SCORM_12

                # Find entry point (launch resource)
                for resource in root.iter():
                    if "resource" in resource.tag.lower():
                        href = resource.get("href")
                        if href:
                            scorm_package.entry_point = href
                            break

                scorm_package.extracted_path = os.path.relpath(extract_dir, settings.MEDIA_ROOT)
                scorm_package.manifest_data = {
                    "title": root.find(".//title", namespaces) or "SCORM Package",
                    "version": scorm_package.scorm_version,
                    "file_count": len(zip_ref.namelist()),
                }
                scorm_package.file_size = os.path.getsize(file_path)
                scorm_package.status = ScormPackage.Status.READY

        except zipfile.BadZipFile as e:
            scorm_package.status = ScormPackage.Status.ERROR
            scorm_package.error_message = "Archivo ZIP invalido o corrupto."
            logger.warning(f"SCORM package {scorm_package.id} tiene ZIP invalido: {e}")
        except ValueError as e:
            scorm_package.status = ScormPackage.Status.ERROR
            scorm_package.error_message = str(e)
            logger.warning(f"Error de validacion en SCORM package {scorm_package.id}: {e}")
        except OSError as e:
            scorm_package.status = ScormPackage.Status.ERROR
            scorm_package.error_message = f"Error de sistema de archivos: {e}"
            logger.error(f"Error de I/O procesando SCORM package {scorm_package.id}: {e}")
        except Exception as e:
            scorm_package.status = ScormPackage.Status.ERROR
            scorm_package.error_message = "Error inesperado procesando el paquete."
            logger.exception(f"Error inesperado procesando SCORM package {scorm_package.id}: {e}")

        scorm_package.save()
        return scorm_package


class ResourceLibraryService:
    """Service for resource library management."""

    @staticmethod
    def add_resource(
        file, user, name: str = None, tags: list = None, category=None
    ) -> ResourceLibrary:
        """Add a resource to the library."""
        mime_type, _ = mimetypes.guess_type(file.name)
        mime_type = mime_type or "application/octet-stream"

        # Determine resource type
        if mime_type.startswith("image/"):
            resource_type = ResourceLibrary.Type.IMAGE
        elif mime_type.startswith("video/"):
            resource_type = ResourceLibrary.Type.VIDEO
        elif mime_type.startswith("audio/"):
            resource_type = ResourceLibrary.Type.AUDIO
        else:
            resource_type = ResourceLibrary.Type.DOCUMENT

        resource = ResourceLibrary.objects.create(
            name=name or file.name,
            resource_type=resource_type,
            file=file,
            file_size=file.size,
            mime_type=mime_type,
            tags=tags or [],
            category=category,
            uploaded_by=user,
        )

        return resource

    @staticmethod
    def search_resources(
        query: str = None,
        resource_type: str = None,
        tags: list = None,
        category_id: int = None,
    ):
        """Search resources in the library."""
        from django.db.models import Q

        queryset = ResourceLibrary.objects.filter(is_public=True)

        if query:
            queryset = queryset.filter(Q(name__icontains=query) | Q(description__icontains=query))

        if resource_type:
            queryset = queryset.filter(resource_type=resource_type)

        if category_id:
            queryset = queryset.filter(category_id=category_id)

        if tags:
            # Filter by tags (using SQLite-compatible approach)
            for tag in tags:
                queryset = queryset.filter(tags__contains=tag)

        return queryset.order_by("-usage_count", "-created_at")

    @staticmethod
    def increment_usage(resource_id: int):
        """Increment the usage count of a resource."""
        ResourceLibrary.objects.filter(id=resource_id).update(
            usage_count=models.F("usage_count") + 1
        )


class CourseScheduleService:
    """Lógica de negocio de la "Programación" de cursos — SD#73.

    Una programación es una convocatoria puntual de un curso YA existente a un
    grupo de personas. Este servicio resuelve la audiencia (personas sueltas +
    perfiles ocupacionales + cargos), materializa los `ScheduleAssignment`,
    reusa/crea el `Enrollment` de cada convocado y avisa a cada uno.
    """

    @staticmethod
    def resolve_audience(users=None, job_profiles=None, job_positions=None):
        """Resuelve la audiencia de una convocatoria a una lista de `User`.

        Tres vías, tal cual las pide el requisito 2 del issue:
          - `users`:         personas específicas (nombre/cédula).
          - `job_profiles`:  `JobProfileType` -> TODOS los usuarios activos con
                             ese `User.job_profile` (perfil ocupacional).
          - `job_positions`: cadenas de `User.job_position` -> TODOS los
                             usuarios activos con ese cargo (texto libre).

        Devuelve ``{user_id: source}`` deduplicado. Cuando una persona entra por
        más de una vía gana la más específica (``user`` > ``profile`` >
        ``position``): el operador la eligió a dedo, esa es la trazabilidad
        honesta de por qué está convocada.

        Solo usuarios ACTIVOS: convocar a alguien desactivado generaría un
        ausente permanente en el reporte de asistencia.
        """
        from django.contrib.auth import get_user_model

        User = get_user_model()
        resolved = {}

        for position in job_positions or []:
            if not position:
                continue
            ids = User.objects.filter(is_active=True, job_position=position).values_list(
                "id", flat=True
            )
            for user_id in ids:
                resolved[user_id] = ScheduleAssignment.Source.POSITION

        for profile in job_profiles or []:
            profile_id = getattr(profile, "pk", profile)
            ids = User.objects.filter(is_active=True, job_profile_id=profile_id).values_list(
                "id", flat=True
            )
            for user_id in ids:
                resolved[user_id] = ScheduleAssignment.Source.PROFILE

        for user in users or []:
            user_id = getattr(user, "pk", user)
            resolved[user_id] = ScheduleAssignment.Source.USER

        return resolved

    @staticmethod
    @transaction.atomic
    def convocar(schedule: CourseSchedule, audience: dict, notify: bool = True) -> dict:
        """Convoca a `audience` (salida de `resolve_audience`) a `schedule`.

        Reglas (requisito "qué pasa si alguien ya está inscrito"):
          - El `Enrollment` se REUSA vía `get_or_create`. Nunca se duplica
            (es único por user+course), nunca se resetea progreso, firma de
            finalización ni estado. Deliberadamente NO se usa
            `EnrollmentService.enroll_user`: ese helper RE-INSCRIBE los
            enrollments `EXPIRED` poniendo `progress=0` y borrando
            `started_at`/`completed_at` — convocar a alguien a un turno no
            puede borrarle el avance que ya tenía.
          - NO se toca `Enrollment.due_date`. Ese campo es un límite DURO
            (`tasks.check_enrollment_deadlines` lo marca `EXPIRED` y obliga a
            "Habilitar de nuevo"); el issue pide una fecha SUGERIDA que no
            bloquee. La fecha vive solo en `schedule.suggested_end_date`.
          - No se exigen prerrequisitos del curso: una convocatoria es una
            decisión administrativa de HSE, mismo criterio que el auto-enroll
            por perfil de `views.my_courses`. El bloqueo secuencial de
            lecciones (`EnrollmentService.is_lesson_accessible`) sigue vigente.
          - Ya convocado a ESTA programación -> no se duplica (UniqueConstraint)
            y no se le vuelve a notificar.

        Devuelve ``{"convocados": [...], "ya_convocados": [...]}`` con los
        `ScheduleAssignment` nuevos y los usuarios que ya estaban.
        """
        from django.contrib.auth import get_user_model

        User = get_user_model()

        existing_ids = set(
            ScheduleAssignment.objects.filter(schedule=schedule).values_list("user_id", flat=True)
        )

        nuevos = []
        ya_convocados = []
        users = User.objects.filter(id__in=list(audience.keys())).select_related("job_profile")

        for user in users:
            if user.id in existing_ids:
                ya_convocados.append(user)
                continue

            enrollment, _created = Enrollment.objects.get_or_create(
                user=user,
                course=schedule.course,
                defaults={
                    "assigned_by": schedule.created_by,
                    "status": Enrollment.Status.ENROLLED,
                },
            )

            assignment = ScheduleAssignment.objects.create(
                schedule=schedule,
                user=user,
                enrollment=enrollment,
                source=audience[user.id],
            )
            nuevos.append(assignment)

        if notify and nuevos:
            for assignment in nuevos:
                CourseScheduleService.notify_assignment(assignment)

        return {"convocados": nuevos, "ya_convocados": ya_convocados}

    @staticmethod
    def notify_assignment(assignment: ScheduleAssignment):
        """Avisa al convocado: "se le asignó este curso y tiene hasta tal fecha".

        Requisito 3 del issue. Usa `NotificationService.create_notification`
        (campos reales del modelo: `subject`/`body`) y deja explícito en el
        cuerpo que pasada la fecha el curso SIGUE disponible, para que la fecha
        se lea como sugerencia y no como bloqueo.

        Nunca levanta: un fallo del subsistema de notificaciones no puede tumbar
        la convocatoria (que ya está persistida en la transacción del caller).
        """
        from apps.notifications.services.notification import NotificationService

        schedule = assignment.schedule
        if schedule.suggested_end_date:
            plazo = (
                f" Tiene hasta el {schedule.suggested_end_date.strftime('%d/%m/%Y')} "
                "(fecha sugerida). Si no alcanza a completarlo en esa fecha, "
                "puede seguir haciéndolo después: el acceso no se bloquea."
            )
        else:
            plazo = " No tiene fecha de finalización sugerida."

        try:
            action_url = reverse("courses:detail", args=[schedule.course_id])
            return NotificationService.create_notification(
                user=assignment.user,
                subject=f"Curso asignado: {schedule.course.title}",
                body=(
                    f"Se le asignó el curso '{schedule.course.title}' dentro de la "
                    f"programación '{schedule.name}'.{plazo}"
                ),
                priority="normal",
                action_url=action_url,
                action_text="Ir al curso",
                metadata={
                    "schedule_id": schedule.id,
                    "course_id": schedule.course_id,
                    "issue": "SD#73",
                },
            )
        except Exception as exc:  # pragma: no cover - defensivo
            logger.warning(
                "No se pudo notificar la convocatoria %s a %s: %s",
                schedule.id,
                assignment.user_id,
                exc,
            )
            return None

    @staticmethod
    def build_schedule_attendance_summary(schedule: CourseSchedule) -> dict:
        """Roster de asistencia de UNA programación (requisito 5 del issue).

        Mismo criterio de "Presente" que el reporte por curso de SD#63
        (`views._build_course_attendance_summary`): presente ⇔ el
        `Enrollment.completion_signature` existe. La diferencia es el universo:
        aquí son SOLO los convocados de esta programación, no todos los
        inscritos del curso — así dos convocatorias del mismo curso no se
        mezclan.

        Devuelve las mismas claves que el helper de SD#63 (`rows`,
        `total_inscritos`, `total_presentes`, `total_ausentes`,
        `porcentaje_asistencia`) para poder alimentar el MISMO template de PDF
        sin duplicar el formato FT-HSEQ-60.
        """
        assignments = (
            ScheduleAssignment.objects.filter(schedule=schedule)
            .select_related("user", "enrollment")
            .order_by("user__first_name", "user__last_name", "user__document_number")
        )

        rows = []
        total_presentes = 0
        for assignment in assignments:
            user = assignment.user
            enrollment = assignment.enrollment
            if enrollment is None:
                enrollment = Enrollment.objects.filter(
                    user=user, course=schedule.course
                ).first()

            presente = bool(enrollment and enrollment.completion_signature)
            if presente:
                total_presentes += 1

            signature_image_url = ""
            if presente:
                try:
                    signature_image_url = enrollment.completion_signature.url
                except Exception:
                    signature_image_url = ""

            rows.append(
                {
                    "user": user,
                    "full_name": user.get_full_name() or user.document_number,
                    "document_number": user.document_number,
                    "job_position": user.job_position,
                    "presente": presente,
                    "estado": "Presente" if presente else "Ausente",
                    "signed_at": enrollment.completion_signed_at if enrollment else None,
                    "signature_image_url": signature_image_url,
                    "source": assignment.get_source_display(),
                }
            )

        total_inscritos = len(rows)
        total_ausentes = total_inscritos - total_presentes
        porcentaje = round(total_presentes / total_inscritos * 100, 1) if total_inscritos else 0.0

        calificacion_promedio = None
        if total_inscritos:
            from django.db.models import Avg

            from apps.assessments.models import AssessmentAttempt

            user_ids = [row["user"].id for row in rows]
            avg = AssessmentAttempt.objects.filter(
                user_id__in=user_ids,
                assessment__course=schedule.course,
                status=AssessmentAttempt.Status.GRADED,
            ).aggregate(avg=Avg("score"))["avg"]
            calificacion_promedio = float(avg) if avg is not None else None

        return {
            "rows": rows,
            "total_inscritos": total_inscritos,
            "total_presentes": total_presentes,
            "total_ausentes": total_ausentes,
            "porcentaje_asistencia": porcentaje,
            "calificacion_promedio": calificacion_promedio,
        }
