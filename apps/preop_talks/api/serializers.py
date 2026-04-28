"""
Serializers for pre-operational talks API.
"""

from rest_framework import serializers

from apps.preop_talks.models import (
    PreopTalk,
    TalkAttachment,
    TalkAttendee,
    TalkTemplate,
)


class TalkTemplateSerializer(serializers.ModelSerializer):
    """Serializer for TalkTemplate model."""

    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = TalkTemplate
        fields = [
            "id",
            "title",
            "description",
            "talk_type",
            "content",
            "key_points",
            "safety_topics",
            "estimated_duration",
            "requires_signature",
            "target_activities",
            "is_active",
            "created_by",
            "created_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def get_created_by_name(self, obj):
        return obj.created_by.get_full_name() if obj.created_by else None

    def create(self, validated_data):
        validated_data["created_by"] = self.context["request"].user
        return super().create(validated_data)


class TalkTemplateListSerializer(serializers.ModelSerializer):
    """Simplified serializer for template lists."""

    class Meta:
        model = TalkTemplate
        fields = [
            "id",
            "title",
            "talk_type",
            "estimated_duration",
            "is_active",
        ]


class TalkAttachmentSerializer(serializers.ModelSerializer):
    """Serializer for TalkAttachment model."""

    class Meta:
        model = TalkAttachment
        fields = [
            "id",
            "file",
            "file_type",
            "original_name",
            "description",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class TalkAttendeeSerializer(serializers.ModelSerializer):
    """Serializer for TalkAttendee model."""

    user_name = serializers.SerializerMethodField()
    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_profile = serializers.CharField(
        source="user.job_profile.code", read_only=True, allow_null=True
    )

    class Meta:
        model = TalkAttendee
        fields = [
            "id",
            "user",
            "user_name",
            "user_email",
            "user_profile",
            "signature",
            "signed_at",
            "understood_content",
            "comments",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def get_user_name(self, obj):
        return obj.user.get_full_name()


class TalkAttendeeSignatureSerializer(serializers.Serializer):
    """Serializer for signing attendance."""

    signature = serializers.ImageField(required=False)
    understood_content = serializers.BooleanField(default=True)
    comments = serializers.CharField(required=False, allow_blank=True)


class PreopTalkSerializer(serializers.ModelSerializer):
    """Serializer for PreopTalk model."""

    template_title = serializers.CharField(source="template.title", read_only=True)
    conducted_by_name = serializers.SerializerMethodField()
    supervisor_name = serializers.SerializerMethodField()
    attendees = TalkAttendeeSerializer(many=True, read_only=True)
    attachments = TalkAttachmentSerializer(many=True, read_only=True)
    attendee_count = serializers.ReadOnlyField()

    class Meta:
        model = PreopTalk
        fields = [
            "id",
            "template",
            "template_title",
            "title",
            "content",
            "key_points",
            "status",
            "project_name",
            "location",
            "work_activity",
            "weather_conditions",
            "special_risks",
            "scheduled_at",
            "started_at",
            "completed_at",
            "duration",
            "conducted_by",
            "conducted_by_name",
            "supervisor",
            "supervisor_name",
            "notes",
            "gps_latitude",
            "gps_longitude",
            "attendees",
            "attachments",
            "attendee_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "started_at",
            "completed_at",
            "duration",
            "created_at",
            "updated_at",
        ]

    def get_conducted_by_name(self, obj):
        return obj.conducted_by.get_full_name() if obj.conducted_by else None

    def get_supervisor_name(self, obj):
        return obj.supervisor.get_full_name() if obj.supervisor else None


class PreopTalkListSerializer(serializers.ModelSerializer):
    """Simplified serializer for talk lists."""

    conducted_by_name = serializers.SerializerMethodField()
    attendee_count = serializers.ReadOnlyField()

    class Meta:
        model = PreopTalk
        fields = [
            "id",
            "title",
            "status",
            "project_name",
            "location",
            "work_activity",
            "scheduled_at",
            "conducted_by_name",
            "attendee_count",
        ]

    def get_conducted_by_name(self, obj):
        return obj.conducted_by.get_full_name() if obj.conducted_by else None


class PreopTalkCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating talks."""

    class Meta:
        model = PreopTalk
        fields = [
            "template",
            "title",
            "content",
            "key_points",
            "project_name",
            "location",
            "work_activity",
            "weather_conditions",
            "special_risks",
            "scheduled_at",
            "supervisor",
            "notes",
            "gps_latitude",
            "gps_longitude",
        ]

    def create(self, validated_data):
        validated_data["conducted_by"] = self.context["request"].user
        return super().create(validated_data)


class AddAttendeeSerializer(serializers.Serializer):
    """Serializer for adding attendees to a talk."""

    user_id = serializers.IntegerField(required=False)
    user_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
    )
