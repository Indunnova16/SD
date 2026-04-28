"""
Serializers for accounts API.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from rest_framework import serializers

from ..models import Contract, Role
from apps.courses.models import JobProfileType

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """Serializer for User model."""

    full_name = serializers.CharField(source="get_full_name", read_only=True)
    job_profile = serializers.SlugRelatedField(
        slug_field="code",
        queryset=JobProfileType.objects.all(),
        allow_null=True,
        required=False,
    )

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "document_type",
            "document_number",
            "phone",
            "photo",
            "job_position",
            "job_profile",
            "hire_date",
            "status",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class UserCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating users."""

    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    job_profile = serializers.SlugRelatedField(
        slug_field="code",
        queryset=JobProfileType.objects.all(),
        allow_null=True,
        required=False,
    )

    class Meta:
        model = User
        fields = [
            "email",
            "password",
            "password_confirm",
            "first_name",
            "last_name",
            "document_type",
            "document_number",
            "phone",
            "job_position",
            "job_profile",
            "hire_date",
        ]

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError({"password": "Las contraseñas no coinciden."})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class UserMinimalSerializer(serializers.ModelSerializer):
    """Minimal user serializer for nested relationships."""

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name"]


class RoleSerializer(serializers.ModelSerializer):
    """Serializer for Role model."""

    user_count = serializers.IntegerField(source="users.count", read_only=True)

    class Meta:
        model = Role
        fields = ["id", "name", "role_type", "description", "user_count"]


class ContractSerializer(serializers.ModelSerializer):
    """Serializer for Contract model."""

    class Meta:
        model = Contract
        fields = [
            "id",
            "code",
            "name",
            "client",
            "description",
            "start_date",
            "end_date",
            "is_active",
        ]


class ChangePasswordSerializer(serializers.Serializer):
    """Serializer for password change."""

    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, validators=[validate_password])

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("La contraseña actual es incorrecta.")
        return value


class LogoutSerializer(serializers.Serializer):
    """Serializer for logout (token blacklist)."""

    refresh = serializers.CharField(required=True, help_text="Refresh token to blacklist")
