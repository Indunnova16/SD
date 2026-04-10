"""
Signals for accounts app.
"""

import logging
from datetime import date

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import JobHistory, User

logger = logging.getLogger(__name__)


@receiver(pre_save, sender=User)
def track_job_profile_changes(sender, instance, **kwargs):
    """
    Track changes to job_profile and job_position for history (USR-08).

    When a user's job profile changes:
    - Record the change in JobHistory
    - Set transient flag for post_save to trigger auto-enrollment
    """
    if not instance.pk:
        # New user, no previous data
        return

    try:
        old_user = User.objects.get(pk=instance.pk)
    except User.DoesNotExist:
        return

    # Check if job profile, position, or employment type changed
    profile_changed = old_user.job_profile != instance.job_profile
    position_changed = old_user.job_position != instance.job_position
    employment_changed = old_user.employment_type != instance.employment_type

    # Set transient flag for post_save auto-enrollment
    instance._job_profile_changed = profile_changed and bool(instance.job_profile)

    if profile_changed or position_changed or employment_changed:
        JobHistory.objects.create(
            user=instance,
            previous_position=old_user.job_position,
            new_position=instance.job_position,
            previous_profile=old_user.job_profile,
            new_profile=instance.job_profile,
            previous_employment_type=old_user.employment_type,
            new_employment_type=instance.employment_type,
            change_date=date.today(),
            reason="Cambio de perfil ocupacional registrado automáticamente",
        )
        logger.info(
            f"Job profile change recorded for {instance.document_number}: "
            f"{old_user.job_profile} → {instance.job_profile}"
        )


def _calculate_due_date(course):
    """Calculate due_date from course.validity_months."""
    from dateutil.relativedelta import relativedelta

    if course.validity_months:
        return date.today() + relativedelta(months=course.validity_months)
    return None


def _auto_enroll_by_profile(user):
    """Auto-enroll user in all published courses matching their job_profile."""
    if not user.job_profile:
        return

    try:
        from apps.courses.models import Course
        from apps.courses.services import EnrollmentService

        courses = Course.objects.published().for_profile(user.job_profile)
        enrolled_count = 0

        for course in courses:
            try:
                due_date = _calculate_due_date(course)
                EnrollmentService.enroll_user(user=user, course=course, due_date=due_date)
                enrolled_count += 1
            except ValueError:
                # Prerequisites not met, skip this course
                logger.debug(
                    f"Skipped auto-enrollment for {user.document_number} "
                    f"in '{course.title}': prerequisites not met"
                )

        if enrolled_count:
            logger.info(
                f"Auto-enrolled {user.document_number} ({user.job_profile}) "
                f"in {enrolled_count} course(s)"
            )
    except ImportError:
        logger.debug("Courses app not available, skipping auto-enrollment")
    except Exception as e:
        logger.warning(f"Error during auto-enrollment for {user.document_number}: {e}")


def _reset_and_reenroll_by_profile(user):
    """Reset all enrollments to ENROLLED and re-assign profile courses (used on reactivation)."""
    if not user.job_profile:
        return

    try:
        from apps.courses.models import CompletionRecord, Course, Enrollment, LessonProgress

        # Save completion records before resetting (permanent audit trail)
        completed_enrollments = Enrollment.objects.filter(
            user=user,
            status__in=[Enrollment.Status.COMPLETED, Enrollment.Status.IN_PROGRESS],
        ).select_related("course")

        records_to_create = []
        for enrollment in completed_enrollments:
            records_to_create.append(
                CompletionRecord(
                    user=user,
                    course=enrollment.course,
                    completed_at=enrollment.completed_at or enrollment.updated_at,
                    progress=enrollment.progress,
                    reset_reason="Reactivación de usuario",
                )
            )
        if records_to_create:
            CompletionRecord.objects.bulk_create(records_to_create)
            logger.info(
                f"Saved {len(records_to_create)} completion record(s) for {user.document_number}"
            )

        # Reset all enrollments back to ENROLLED so user must redo them
        reset_count = (
            Enrollment.objects.filter(user=user)
            .exclude(status=Enrollment.Status.ENROLLED)
            .update(
                status=Enrollment.Status.ENROLLED,
                progress=0,
                started_at=None,
                completed_at=None,
            )
        )
        if reset_count:
            logger.info(
                f"Reset {reset_count} enrollment(s) for reactivated user {user.document_number}"
            )

        # Also reset lesson progress
        LessonProgress.objects.filter(enrollment__user=user).update(
            is_completed=False,
            progress_percent=0,
            time_spent=0,
            completed_at=None,
        )

        # Enroll in any new courses for the profile
        courses = Course.objects.published().for_profile(user.job_profile)
        new_count = 0
        for course in courses:
            try:
                _, created = Enrollment.objects.get_or_create(
                    user=user,
                    course=course,
                    defaults={"status": Enrollment.Status.ENROLLED},
                )
                if created:
                    new_count += 1
            except Exception:
                pass

        if new_count:
            logger.info(
                f"Added {new_count} new enrollment(s) for reactivated user {user.document_number}"
            )
    except ImportError:
        logger.debug("Courses app not available, skipping re-enrollment")
    except Exception as e:
        logger.warning(f"Error during re-enrollment for {user.document_number}: {e}")


@receiver(post_save, sender=User)
def user_post_save(sender, instance, created, **kwargs):
    """
    Signal handler for user creation and updates.

    On creation:
        - Creates UserPoints record for gamification
        - Creates UserNotificationPreference with defaults
        - Auto-enrolls in courses matching job_profile
        - Logs audit entry

    On update:
        - If job_profile changed, auto-enrolls in new profile's courses
        - Logs significant changes (email, status)
    """
    if created:
        # Create gamification points record
        try:
            from apps.gamification.models import UserPoints

            UserPoints.objects.get_or_create(user=instance)
            logger.debug(f"Created UserPoints for user: {instance.email}")
        except ImportError:
            logger.debug("Gamification app not available, skipping UserPoints creation")
        except Exception as e:
            logger.warning(f"Failed to create UserPoints for {instance.email}: {e}")

        # Create notification preferences with defaults
        try:
            from apps.notifications.models import UserNotificationPreference

            UserNotificationPreference.objects.get_or_create(user=instance)
            logger.debug(f"Created NotificationPreference for user: {instance.email}")
        except ImportError:
            logger.debug("Notifications app not available, skipping preference creation")
        except Exception as e:
            logger.warning(f"Failed to create NotificationPreference for {instance.email}: {e}")

        # Auto-enroll in courses matching job_profile
        _auto_enroll_by_profile(instance)

        # Audit log for new user creation
        logger.info(f"New user created: {instance.email} (ID: {instance.id})")
    else:
        # Auto-enroll if job_profile changed
        if getattr(instance, "_job_profile_changed", False):
            _auto_enroll_by_profile(instance)

        # Log significant updates
        update_fields = kwargs.get("update_fields")

        if update_fields:
            significant_fields = {"email", "is_active", "is_staff", "is_superuser"}
            changed_significant = significant_fields.intersection(set(update_fields))

            if changed_significant:
                logger.info(
                    f"User {instance.email} (ID: {instance.id}) updated: "
                    f"changed fields: {', '.join(changed_significant)}"
                )
            else:
                logger.debug(f"User updated: {instance.email} (ID: {instance.id})")
        else:
            # When update_fields is None, we don't know what changed
            logger.debug(f"User updated: {instance.email} (ID: {instance.id})")
