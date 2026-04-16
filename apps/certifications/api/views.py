"""
ViewSets for certifications API.
"""

import uuid
from datetime import timedelta

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import User
from apps.certifications.models import (
    Certificate,
    CertificateTemplate,
    CertificateVerification,
)
from apps.courses.models import Course

from .serializers import (
    CertificateCreateSerializer,
    CertificateListSerializer,
    CertificateRevokeSerializer,
    CertificateSerializer,
    CertificateTemplateListSerializer,
    CertificateTemplateSerializer,
    CertificateVerificationSerializer,
    CertificateVerifySerializer,
    MyCertificateSerializer,
)


class CertificateTemplateViewSet(viewsets.ModelViewSet):
    """ViewSet for managing certificate templates."""

    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = CertificateTemplate.objects.all()

        # Filter by active status
        is_active = self.request.query_params.get("active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")

        # Search
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(Q(name__icontains=search) | Q(description__icontains=search))

        return queryset.order_by("name")

    def get_serializer_class(self):
        if self.action == "list":
            return CertificateTemplateListSerializer
        return CertificateTemplateSerializer


class CertificateViewSet(viewsets.ModelViewSet):
    """ViewSet for managing certificates."""

    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Certificate.objects.select_related("user", "course", "template")

        # Filter by user
        user_id = self.request.query_params.get("user")
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        # Filter by course
        course_id = self.request.query_params.get("course")
        if course_id:
            queryset = queryset.filter(course_id=course_id)

        # Filter by status
        cert_status = self.request.query_params.get("status")
        if cert_status:
            queryset = queryset.filter(status=cert_status)

        # Search by certificate number
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(certificate_number__icontains=search)
                | Q(user__email__icontains=search)
                | Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
            )

        # Non-staff see only their own certificates
        if not self.request.user.is_staff:
            queryset = queryset.filter(user=self.request.user)

        return queryset.order_by("-issued_at", "-created_at")

    def get_serializer_class(self):
        if self.action == "list":
            return CertificateListSerializer
        return CertificateSerializer

    @action(detail=False, methods=["post"])
    def issue(self, request):
        """Issue a new certificate."""
        if not request.user.is_staff:
            return Response(
                {"error": "Solo personal autorizado puede emitir certificados"},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = CertificateCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_id = serializer.validated_data["user_id"]
        course_id = serializer.validated_data["course_id"]
        template_id = serializer.validated_data.get("template_id")
        score = serializer.validated_data.get("score")

        user = get_object_or_404(User, pk=user_id)
        course = get_object_or_404(Course, pk=course_id)

        template = None
        if template_id:
            template = get_object_or_404(CertificateTemplate, pk=template_id)

        # Check if certificate already exists
        existing = Certificate.objects.filter(
            user=user,
            course=course,
            status__in=[Certificate.Status.PENDING, Certificate.Status.ISSUED],
        ).first()

        if existing:
            return Response(
                {"error": "El usuario ya tiene un certificado para este curso"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Generate certificate number
        certificate_number = self._generate_certificate_number()

        # Create certificate
        certificate = Certificate.objects.create(
            user=user,
            course=course,
            template=template,
            certificate_number=certificate_number,
            score=score,
            status=Certificate.Status.ISSUED,
            issued_at=timezone.now(),
            expires_at=timezone.now() + timedelta(days=365 * 2),  # 2 years
        )

        # Generate verification URL
        certificate.verification_url = self._generate_verification_url(certificate)
        certificate.save()

        return Response(
            CertificateSerializer(certificate).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def revoke(self, request, pk=None):
        """Revoke a certificate."""
        if not request.user.is_staff:
            return Response(
                {"error": "Solo personal autorizado puede revocar certificados"},
                status=status.HTTP_403_FORBIDDEN,
            )

        certificate = self.get_object()

        if certificate.status == Certificate.Status.REVOKED:
            return Response(
                {"error": "El certificado ya está revocado"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = CertificateRevokeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        certificate.status = Certificate.Status.REVOKED
        certificate.revoked_at = timezone.now()
        certificate.revoked_reason = serializer.validated_data["reason"]
        certificate.save()

        return Response(CertificateSerializer(certificate).data)

    @action(detail=False, methods=["post"], permission_classes=[permissions.AllowAny])
    def verify(self, request):
        """Verify a certificate by its number."""
        serializer = CertificateVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        certificate_number = serializer.validated_data["certificate_number"]

        try:
            certificate = Certificate.objects.select_related("user", "course").get(
                certificate_number=certificate_number
            )
        except Certificate.DoesNotExist:
            return Response(
                {"valid": False, "error": "Certificado no encontrado"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Log verification
        ip_address = request.META.get("REMOTE_ADDR", "")
        user_agent = request.headers.get("user-agent", "")

        is_valid = certificate.status == Certificate.Status.ISSUED
        if certificate.expires_at and certificate.expires_at < timezone.now():
            is_valid = False

        CertificateVerification.objects.create(
            certificate=certificate,
            ip_address=ip_address,
            user_agent=user_agent,
            is_valid=is_valid,
        )

        return Response(
            {
                "valid": is_valid,
                "certificate_number": certificate.certificate_number,
                "user_name": certificate.user.get_full_name(),
                "course_title": certificate.course.title,
                "issued_at": certificate.issued_at,
                "expires_at": certificate.expires_at,
                "status": certificate.status,
            }
        )

    @action(detail=False, methods=["get"])
    def my_certificates(self, request):
        """Get current user's certificates."""
        certificates = (
            Certificate.objects.filter(
                user=request.user,
                status=Certificate.Status.ISSUED,
            )
            .select_related("course")
            .order_by("-issued_at")
        )

        serializer = MyCertificateSerializer(certificates, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        """Get certificate download URL."""
        certificate = self.get_object()

        if certificate.user != request.user and not request.user.is_staff:
            return Response(
                {"error": "No autorizado"},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not certificate.certificate_file:
            return Response(
                {"error": "El archivo del certificado no está disponible"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {"download_url": request.build_absolute_uri(certificate.certificate_file.url)}
        )

    @action(detail=True, methods=["get"])
    def verifications(self, request, pk=None):
        """Get verification history for a certificate."""
        if not request.user.is_staff:
            return Response(
                {"error": "Solo personal autorizado puede ver el historial"},
                status=status.HTTP_403_FORBIDDEN,
            )

        certificate = self.get_object()
        verifications = certificate.verifications.order_by("-verified_at")[:50]

        serializer = CertificateVerificationSerializer(verifications, many=True)
        return Response(serializer.data)

    def _generate_certificate_number(self):
        """Generate a unique certificate number."""
        prefix = "SD"
        year = timezone.now().strftime("%Y")
        unique_id = uuid.uuid4().hex[:8].upper()
        return f"{prefix}-{year}-{unique_id}"

    def _generate_verification_url(self, certificate):
        """Generate verification URL for a certificate."""
        # This would typically use the actual domain
        return f"/verify/{certificate.certificate_number}/"
