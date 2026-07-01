"""
Business logic services for certifications.
"""

import logging
import uuid
from datetime import timedelta
from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone

from apps.certifications.models import (
    Certificate,
    CertificateTemplate,
    CertificateVerification,
)
from apps.courses.models import Course, Enrollment

logger = logging.getLogger(__name__)


class CertificateService:
    """Service for certificate operations."""

    @staticmethod
    def generate_certificate_number() -> str:
        """
        Generate a unique certificate number.
        Format: SD-YYYYMM-XXXXXXXX
        """
        now = timezone.now()
        date_part = now.strftime("%Y%m")
        unique_part = uuid.uuid4().hex[:8].upper()
        return f"SD-{date_part}-{unique_part}"

    @staticmethod
    def calculate_expiry_date(course: Course) -> timezone.datetime | None:
        """
        Calculate certificate expiry date based on course validity.
        """
        if not course.validity_months:
            return None

        return timezone.now() + timedelta(days=course.validity_months * 30)

    @staticmethod
    def can_issue_certificate(user, course: Course) -> dict:
        """
        Check if a certificate can be issued for a user/course.
        """
        result = {
            "can_issue": True,
            "reason": None,
            "enrollment": None,
            "existing_certificate": None,
        }

        # Check enrollment
        enrollment = Enrollment.objects.filter(
            user=user,
            course=course,
        ).first()

        if not enrollment:
            result["can_issue"] = False
            result["reason"] = "El usuario no está inscrito en este curso"
            return result

        result["enrollment"] = enrollment

        if enrollment.status != Enrollment.Status.COMPLETED:
            result["can_issue"] = False
            result["reason"] = "El usuario no ha completado el curso"
            return result

        # Check existing valid certificate
        existing = Certificate.objects.filter(
            user=user,
            course=course,
            status=Certificate.Status.ISSUED,
        ).first()

        if existing:
            if existing.expires_at and existing.expires_at > timezone.now():
                result["can_issue"] = False
                result["reason"] = "Ya existe un certificado válido para este curso"
                result["existing_certificate"] = existing
                return result

        return result

    @staticmethod
    @transaction.atomic
    def issue_certificate(
        user,
        course: Course,
        template: CertificateTemplate = None,
        score: float = None,
        metadata: dict = None,
    ) -> Certificate:
        """
        Issue a certificate for a user who completed a course.
        """
        # Validate
        check = CertificateService.can_issue_certificate(user, course)
        if not check["can_issue"]:
            raise ValueError(check["reason"])

        # Get score from enrollment if not provided
        if score is None:
            enrollment = check["enrollment"]
            score = float(enrollment.progress) if enrollment else 100.0

        # Get or select template
        if not template:
            template = CertificateTemplate.objects.filter(is_active=True).first()

        # Create certificate
        certificate = Certificate.objects.create(
            user=user,
            course=course,
            template=template,
            certificate_number=CertificateService.generate_certificate_number(),
            status=Certificate.Status.PENDING,
            score=score,
            expires_at=CertificateService.calculate_expiry_date(course),
            metadata=metadata or {},
        )

        # Generate the certificate
        CertificateService.generate_certificate_file(certificate)

        return certificate

    @staticmethod
    def generate_certificate_file(certificate: Certificate) -> Certificate:
        """
        Generate the PDF file and QR code for a certificate.
        """
        try:
            # Generate verification URL
            base_url = getattr(settings, "SITE_URL", "https://lms.sd.com.co")
            certificate.verification_url = (
                f"{base_url}/certifications/verify/{certificate.certificate_number}/"
            )

            # Generate QR code
            CertificateService._generate_qr_code(certificate)

            # Generate PDF
            CertificateService._generate_pdf(certificate)

            # Update status
            certificate.status = Certificate.Status.ISSUED
            certificate.issued_at = timezone.now()
            certificate.save()

            logger.info(f"Certificate generated: {certificate.certificate_number}")

        except ImportError as e:
            logger.warning(f"Dependencia faltante para generar certificado {certificate.id}: {e}")
            certificate.metadata["generation_error"] = f"Dependencia faltante: {e}"
            certificate.save()
            raise
        except OSError as e:
            logger.error(f"Error de I/O generando certificado {certificate.id}: {e}")
            certificate.metadata["generation_error"] = f"Error de archivo: {e}"
            certificate.save()
            raise
        except Exception as e:
            logger.exception(f"Error inesperado generando certificado {certificate.id}: {e}")
            certificate.metadata["generation_error"] = "Error inesperado durante la generacion."
            certificate.save()
            raise

        return certificate

    @staticmethod
    def _generate_qr_code(certificate: Certificate) -> None:
        """
        Generate QR code for certificate verification.
        """
        try:
            import qrcode

            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=10,
                border=4,
            )
            qr.add_data(certificate.verification_url)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")

            # Save to buffer
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            buffer.seek(0)

            # Save to model
            filename = f"qr_{certificate.certificate_number}.png"
            certificate.qr_code.save(filename, ContentFile(buffer.read()), save=False)

        except ImportError:
            logger.warning("Biblioteca qrcode no instalada, saltando generacion de QR")
        except OSError as e:
            logger.error(f"Error de I/O generando codigo QR para certificado {certificate.id}: {e}")
        except Exception as e:
            logger.exception(
                f"Error inesperado generando codigo QR para certificado {certificate.id}: {e}"
            )

    @staticmethod
    def _generate_pdf(certificate: Certificate) -> None:
        """
        Generate PDF certificate from template.
        """
        try:
            from weasyprint import HTML

            # Prepare context
            context = {
                "certificate": certificate,
                "user": certificate.user,
                "course": certificate.course,
                "template": certificate.template,
                "issued_date": certificate.issued_at or timezone.now(),
                "expires_date": certificate.expires_at,
                "verification_url": certificate.verification_url,
                "certificate_number": certificate.certificate_number,
            }

            # Render HTML
            if certificate.template and certificate.template.template_file:
                # Use custom template
                with certificate.template.template_file.open("r") as f:
                    template_content = f.read()
                from django.template import Context, Template

                html_content = Template(template_content).render(Context(context))
            else:
                # Use default template
                html_content = render_to_string(
                    "certifications/certificate_template.html",
                    context,
                )

            # Generate PDF
            pdf = HTML(string=html_content).write_pdf()

            # Save to model
            filename = f"cert_{certificate.certificate_number}.pdf"
            certificate.certificate_file.save(filename, ContentFile(pdf), save=False)

        except ImportError:
            logger.warning("weasyprint no esta instalado, usando PDF placeholder")
            # Create a simple placeholder
            placeholder = CertificateService._generate_placeholder_pdf(certificate)
            filename = f"cert_{certificate.certificate_number}.pdf"
            certificate.certificate_file.save(filename, ContentFile(placeholder), save=False)
        except OSError as e:
            logger.error(f"Error de I/O generando PDF para certificado {certificate.id}: {e}")
            raise
        except Exception as e:
            logger.exception(
                f"Error inesperado generando PDF para certificado {certificate.id}: {e}"
            )
            raise

    @staticmethod
    def _generate_placeholder_pdf(certificate: Certificate) -> bytes:
        """
        Generate a simple placeholder PDF when weasyprint is not available.
        """
        try:
            from reportlab.lib.pagesizes import landscape, letter
            from reportlab.lib.units import inch
            from reportlab.pdfgen import canvas

            buffer = BytesIO()
            c = canvas.Canvas(buffer, pagesize=landscape(letter))
            width, height = landscape(letter)

            # Title
            c.setFont("Helvetica-Bold", 36)
            c.drawCentredString(width / 2, height - 2 * inch, "CERTIFICADO")

            # Course
            c.setFont("Helvetica", 18)
            c.drawCentredString(width / 2, height - 3 * inch, f"Curso: {certificate.course.title}")

            # User
            c.setFont("Helvetica", 18)
            c.drawCentredString(
                width / 2,
                height - 3.5 * inch,
                f"Otorgado a: {certificate.user.get_full_name()}",
            )

            # Certificate number
            c.setFont("Helvetica", 12)
            c.drawCentredString(
                width / 2, height - 4.5 * inch, f"No: {certificate.certificate_number}"
            )

            # Date
            date_str = timezone.now().strftime("%d de %B de %Y")
            c.drawCentredString(width / 2, height - 5 * inch, f"Fecha: {date_str}")

            c.save()
            buffer.seek(0)
            return buffer.read()

        except ImportError:
            logger.warning("reportlab not installed, returning empty PDF")
            return b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj 3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj xref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n0000000052 00000 n\n0000000101 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n176\n%%EOF"

    @staticmethod
    def verify_certificate(
        certificate_number: str,
        ip_address: str = None,
        user_agent: str = "",
    ) -> dict:
        """
        Verify a certificate by its number.
        """
        certificate = Certificate.objects.filter(certificate_number=certificate_number).first()

        if not certificate:
            return {
                "valid": False,
                "reason": "Certificado no encontrado",
                "certificate": None,
            }

        # Log verification attempt
        CertificateVerification.objects.create(
            certificate=certificate,
            ip_address=ip_address,
            user_agent=user_agent,
            is_valid=certificate.status == Certificate.Status.ISSUED,
        )

        # Check status
        if certificate.status == Certificate.Status.REVOKED:
            return {
                "valid": False,
                "reason": "Este certificado ha sido revocado",
                "revoked_at": certificate.revoked_at.isoformat()
                if certificate.revoked_at
                else None,
                "revoked_reason": certificate.revoked_reason,
                "certificate": None,
            }

        if certificate.status == Certificate.Status.EXPIRED:
            return {
                "valid": False,
                "reason": "Este certificado ha expirado",
                "expired_at": certificate.expires_at.isoformat()
                if certificate.expires_at
                else None,
                "certificate": None,
            }

        # Check expiry
        if certificate.expires_at and certificate.expires_at < timezone.now():
            certificate.status = Certificate.Status.EXPIRED
            certificate.save()
            return {
                "valid": False,
                "reason": "Este certificado ha expirado",
                "expired_at": certificate.expires_at.isoformat(),
                "certificate": None,
            }

        if certificate.status != Certificate.Status.ISSUED:
            return {
                "valid": False,
                "reason": "Este certificado no está activo",
                "certificate": None,
            }

        return {
            "valid": True,
            "certificate": {
                "number": certificate.certificate_number,
                "user_name": certificate.user.get_full_name(),
                "course_title": certificate.course.title,
                "issued_at": certificate.issued_at.isoformat() if certificate.issued_at else None,
                "expires_at": certificate.expires_at.isoformat()
                if certificate.expires_at
                else None,
                "score": float(certificate.score) if certificate.score else None,
            },
        }

    @staticmethod
    @transaction.atomic
    def revoke_certificate(
        certificate: Certificate,
        reason: str,
        revoked_by=None,
    ) -> Certificate:
        """
        Revoke a certificate.
        """
        if certificate.status == Certificate.Status.REVOKED:
            raise ValueError("El certificado ya está revocado")

        certificate.status = Certificate.Status.REVOKED
        certificate.revoked_at = timezone.now()
        certificate.revoked_reason = reason

        if revoked_by:
            certificate.metadata["revoked_by"] = revoked_by.id

        certificate.save()

        logger.info(f"Certificate revoked: {certificate.certificate_number}")
        return certificate

    @staticmethod
    @transaction.atomic
    def reissue_certificate(
        certificate: Certificate,
        reason: str = "",
    ) -> Certificate:
        """
        Reissue a certificate (for renewals or corrections).
        """
        # Create new certificate
        new_certificate = Certificate.objects.create(
            user=certificate.user,
            course=certificate.course,
            template=certificate.template,
            certificate_number=CertificateService.generate_certificate_number(),
            status=Certificate.Status.PENDING,
            score=certificate.score,
            expires_at=CertificateService.calculate_expiry_date(certificate.course),
            metadata={
                "reissued_from": certificate.certificate_number,
                "reissue_reason": reason,
            },
        )

        # Revoke old certificate
        CertificateService.revoke_certificate(
            certificate,
            reason=f"Reemitido como {new_certificate.certificate_number}: {reason}",
        )

        # Generate new certificate
        CertificateService.generate_certificate_file(new_certificate)

        return new_certificate

    @staticmethod
    def get_expiring_certificates(days_ahead: int = 30):
        """
        Get certificates expiring within the specified days.
        """
        now = timezone.now()
        deadline = now + timedelta(days=days_ahead)

        return Certificate.objects.filter(
            status=Certificate.Status.ISSUED,
            expires_at__isnull=False,
            expires_at__gte=now,
            expires_at__lte=deadline,
        ).select_related("user", "course")

    @staticmethod
    def get_user_certificates(user, include_expired: bool = False):
        """
        Get all certificates for a user.
        """
        queryset = Certificate.objects.filter(user=user)

        if not include_expired:
            queryset = queryset.exclude(status=Certificate.Status.EXPIRED)

        return queryset.select_related("course", "template").order_by("-issued_at")

    @staticmethod
    def check_and_expire_certificates():
        """
        Check and mark expired certificates.
        Called periodically by a scheduled task.
        """
        now = timezone.now()

        expired = Certificate.objects.filter(
            status=Certificate.Status.ISSUED,
            expires_at__lt=now,
        )

        count = expired.update(status=Certificate.Status.EXPIRED)
        if count > 0:
            logger.info(f"Marked {count} certificates as expired")

        return count

    @staticmethod
    def get_certificate_statistics(course: Course = None) -> dict:
        """
        Get certificate statistics, optionally filtered by course.
        """
        queryset = Certificate.objects.all()

        if course:
            queryset = queryset.filter(course=course)

        total = queryset.count()
        issued = queryset.filter(status=Certificate.Status.ISSUED).count()
        revoked = queryset.filter(status=Certificate.Status.REVOKED).count()
        expired = queryset.filter(status=Certificate.Status.EXPIRED).count()
        pending = queryset.filter(status=Certificate.Status.PENDING).count()

        return {
            "total": total,
            "issued": issued,
            "revoked": revoked,
            "expired": expired,
            "pending": pending,
            "active_rate": (issued / total * 100) if total > 0 else 0,
        }


class CertificateTemplateService:
    """Service for managing certificate templates."""

    @staticmethod
    def preview_template(
        template: CertificateTemplate,
        sample_data: dict = None,
    ) -> str:
        """
        Generate a preview of a certificate template.
        """
        default_data = {
            "certificate_number": "SD-PREVIEW-00000000",
            "user_name": "Juan Ejemplo",
            "course_title": "Curso de Ejemplo",
            "issued_date": timezone.now().strftime("%d de %B de %Y"),
            "expires_date": (timezone.now() + timedelta(days=365)).strftime("%d de %B de %Y"),
            "score": 95.0,
            "verification_url": "https://lms.sd.com.co/certifications/verify/SD-PREVIEW-00000000/",
        }

        if sample_data:
            default_data.update(sample_data)

        # Render template
        if template.template_file:
            with template.template_file.open("r") as f:
                from django.template import Context, Template

                html = Template(f.read()).render(Context(default_data))
        else:
            html = render_to_string(
                "certifications/certificate_template.html",
                default_data,
            )

        return html

    @staticmethod
    @transaction.atomic
    def duplicate_template(
        template: CertificateTemplate,
        new_name: str = None,
    ) -> CertificateTemplate:
        """
        Duplicate a certificate template.
        """
        new_template = CertificateTemplate.objects.create(
            name=new_name or f"{template.name} (Copia)",
            description=template.description,
            signer_name=template.signer_name,
            signer_title=template.signer_title,
            is_active=False,  # Start as inactive
            metadata=template.metadata.copy() if template.metadata else {},
        )

        # Copy files if they exist
        if template.template_file:
            new_template.template_file.save(
                template.template_file.name,
                template.template_file.file,
                save=True,
            )

        if template.background_image:
            new_template.background_image.save(
                template.background_image.name,
                template.background_image.file,
                save=True,
            )

        if template.logo:
            new_template.logo.save(
                template.logo.name,
                template.logo.file,
                save=True,
            )

        if template.signature_image:
            new_template.signature_image.save(
                template.signature_image.name,
                template.signature_image.file,
                save=True,
            )

        return new_template
