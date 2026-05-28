"""
Signals for certifications app.

When an Enrollment transitions to COMPLETED, automatically issue a certificate
for the (user, course) pair if one doesn't already exist (idempotent).
"""

import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(
    post_save,
    sender="courses.Enrollment",
    dispatch_uid="cert_on_enrollment_complete",
)
def issue_certificate_on_enrollment_completed(sender, instance, created, **kwargs):
    """
    Auto-issue a certificate when Enrollment.status becomes COMPLETED.

    Idempotent: if a valid ISSUED certificate already exists for this
    (user, course), does nothing. Uses transaction.on_commit so the side-effect
    runs only if the outer transaction succeeds.
    """
    # Local imports avoid AppRegistryNotReady on Django startup
    from apps.certifications.models import Certificate
    from apps.certifications.services import CertificateService
    from apps.courses.models import Enrollment

    if instance.status != Enrollment.Status.COMPLETED:
        return

    # Already-issued check: if a valid ISSUED certificate exists, skip.
    existing = Certificate.objects.filter(
        user_id=instance.user_id,
        course_id=instance.course_id,
        status=Certificate.Status.ISSUED,
    ).exists()
    if existing:
        return

    def _issue():
        try:
            CertificateService.issue_certificate(
                user=instance.user,
                course=instance.course,
            )
            logger.info(
                "Auto-issued certificate for enrollment %s (user=%s, course=%s)",
                instance.pk,
                instance.user_id,
                instance.course_id,
            )
        except ValueError as e:
            logger.warning(
                "Cannot auto-issue certificate for enrollment %s: %s",
                instance.pk,
                e,
            )
        except Exception:
            logger.exception(
                "Unexpected error auto-issuing certificate for enrollment %s",
                instance.pk,
            )

    transaction.on_commit(_issue)
