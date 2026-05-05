"""
API views for accounts app.
"""

import logging

from django.contrib.auth import get_user_model

from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

logger = logging.getLogger(__name__)

from .serializers import (
    ChangePasswordSerializer,
    LogoutSerializer,
    UserCreateSerializer,
    UserSerializer,
)

User = get_user_model()


class CurrentUserView(generics.RetrieveUpdateAPIView):
    """Get or update the current authenticated user."""

    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class RegisterView(generics.CreateAPIView):
    """Register a new user (admin only)."""

    serializer_class = UserCreateSerializer
    permission_classes = [permissions.IsAdminUser]


class ChangePasswordView(generics.UpdateAPIView):
    """Change password for the current user."""

    serializer_class = ChangePasswordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = self.get_object()
        user.set_password(serializer.validated_data["new_password"])
        user.save()

        return Response({"message": "Contraseña actualizada correctamente."})


class LogoutView(APIView):
    """Logout by blacklisting the refresh token."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            refresh_token = serializer.validated_data["refresh"]
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(
                {"message": "Sesion cerrada correctamente."},
                status=status.HTTP_200_OK,
            )
        except TokenError as e:
            logger.warning(f"Token invalido o expirado durante logout: {e}")
            return Response(
                {"error": "Token invalido o ya revocado."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.exception(f"Error inesperado durante logout: {e}")
            return Response(
                {"error": "Error interno del servidor."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class UserViewSet(viewsets.ModelViewSet):
    """ViewSet for User CRUD operations."""

    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ["status", "job_profile__code", "is_active"]
    search_fields = ["email", "first_name", "last_name", "document_number"]
    ordering_fields = ["last_name", "first_name", "hire_date", "created_at"]
    ordering = ["last_name", "first_name"]

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        return UserSerializer

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        """Activate a user."""
        user = self.get_object()
        user.is_active = True
        user.status = User.Status.ACTIVE
        user.save()
        return Response({"status": "Usuario activado"})

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        """Deactivate a user."""
        user = self.get_object()
        user.is_active = False
        user.status = User.Status.INACTIVE
        user.save()
        return Response({"status": "Usuario desactivado"})


class ImportUsersView(APIView):
    """Import users from CSV/Excel file."""

    parser_classes = [MultiPartParser]
    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        file = request.FILES.get("file")
        if not file:
            return Response(
                {"error": "No se proporcionó archivo"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            import pandas as pd
            import io

            # Detect file type and read
            if file.name.endswith(".csv"):
                df = pd.read_csv(io.StringIO(file.read().decode("utf-8")))
            elif file.name.endswith((".xlsx", ".xls")):
                df = pd.read_excel(io.BytesIO(file.read()))
            else:
                return Response(
                    {"error": "Archivo debe ser CSV o Excel (.xlsx, .xls)"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Validate required columns
            required_cols = {"email"}
            if not required_cols.issubset(set(df.columns)):
                return Response(
                    {"error": f"Columnas requeridas: {', '.join(required_cols)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Process users
            created_count = 0
            updated_count = 0
            errors = []

            for idx, row in df.iterrows():
                email = str(row.get("email", "")).strip()
                if not email:
                    errors.append(f"Fila {idx + 2}: email vacío")
                    continue

                user_data = {
                    "first_name": str(row.get("first_name", ""))[:30],
                    "last_name": str(row.get("last_name", ""))[:30],
                    "email": email,
                }

                user, created = User.objects.get_or_create(email=email, defaults=user_data)
                if created:
                    created_count += 1
                else:
                    updated_count += 1

            return Response(
                {
                    "message": "Importación completada",
                    "created": created_count,
                    "updated": updated_count,
                    "errors": errors,
                },
                status=status.HTTP_201_CREATED,
            )

        except ImportError:
            return Response(
                {"error": "pandas no está instalado. Contactar al administrador."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception as e:
            logger.exception("Error importing users")
            return Response(
                {"error": f"Error al procesar archivo: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
