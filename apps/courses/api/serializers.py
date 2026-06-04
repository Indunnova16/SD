"""
Serializers for courses API.
"""

from rest_framework import serializers

from apps.courses.models import (
    Category,
    Course,
    CourseVersion,
    Enrollment,
    Lesson,
    LessonProgress,
    MediaAsset,
    Module,
    ResourceLibrary,
    ScormAttempt,
    ScormPackage,
)


class CategorySerializer(serializers.ModelSerializer):
    """Serializer for Category model."""

    course_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "icon",
            "color",
            "order",
            "is_active",
            "course_count",
        ]
        read_only_fields = ["id"]

    def get_course_count(self, obj):
        return obj.courses.filter(status="published").count()


class CategoryListSerializer(serializers.ModelSerializer):
    """Simplified serializer for category lists."""

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "icon", "color"]


class LessonSerializer(serializers.ModelSerializer):
    """Serializer for Lesson model."""

    class Meta:
        model = Lesson
        fields = [
            "id",
            "title",
            "description",
            "lesson_type",
            "content",
            "content_file",
            "video_url",
            "duration",
            "order",
            "is_mandatory",
            "is_offline_available",
            "metadata",
        ]
        read_only_fields = ["id"]


class LessonListSerializer(serializers.ModelSerializer):
    """Simplified serializer for lesson lists."""

    class Meta:
        model = Lesson
        fields = [
            "id",
            "title",
            "lesson_type",
            "duration",
            "order",
            "is_mandatory",
        ]


class ModuleSerializer(serializers.ModelSerializer):
    """Serializer for Module model."""

    lessons = LessonSerializer(many=True, read_only=True)
    lesson_count = serializers.SerializerMethodField()

    class Meta:
        model = Module
        fields = [
            "id",
            "title",
            "description",
            "order",
            "lessons",
            "lesson_count",
        ]
        read_only_fields = ["id"]

    def get_lesson_count(self, obj):
        return obj.lessons.count()


class ModuleListSerializer(serializers.ModelSerializer):
    """Simplified serializer for module lists."""

    lesson_count = serializers.SerializerMethodField()

    class Meta:
        model = Module
        fields = ["id", "title", "order", "lesson_count"]

    def get_lesson_count(self, obj):
        return obj.lessons.count()


class CourseSerializer(serializers.ModelSerializer):
    """Serializer for Course model."""

    modules = ModuleSerializer(many=True, read_only=True)
    total_duration = serializers.ReadOnlyField()
    created_by_name = serializers.SerializerMethodField()
    category_name = serializers.SerializerMethodField()
    category_detail = CategoryListSerializer(source="category", read_only=True)
    contract_names = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = [
            "id",
            "code",
            "title",
            "description",
            "objectives",
            "course_type",
            "thumbnail",
            "status",
            "version",
            "target_profiles",
            "prerequisites",
            "validity_months",
            "category",
            "category_name",
            "category_detail",
            "contracts",
            "contract_names",
            "created_by",
            "created_by_name",
            "published_at",
            "total_duration",
            "modules",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "published_at", "created_at", "updated_at"]

    def get_created_by_name(self, obj):
        return obj.created_by.get_full_name() if obj.created_by else None

    def get_category_name(self, obj):
        return obj.category.name if obj.category else None

    def get_contract_names(self, obj):
        return [c.name for c in obj.contracts.all()]


class CourseListSerializer(serializers.ModelSerializer):
    """Simplified serializer for course lists."""

    total_duration = serializers.ReadOnlyField()
    module_count = serializers.SerializerMethodField()
    enrollment_count = serializers.SerializerMethodField()
    category_name = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = [
            "id",
            "code",
            "title",
            "course_type",
            "status",
            "total_duration",
            "thumbnail",
            "category",
            "category_name",
            "module_count",
            "enrollment_count",
        ]

    def get_module_count(self, obj):
        return obj.modules.count()

    def get_enrollment_count(self, obj):
        return obj.enrollments.count()

    def get_category_name(self, obj):
        return obj.category.name if obj.category else None


class CourseCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating courses."""

    class Meta:
        model = Course
        fields = [
            "code",
            "title",
            "description",
            "objectives",
            "course_type",
            "thumbnail",
            "target_profiles",
            "prerequisites",
            "validity_months",
            "category",
            "contracts",
        ]

    def create(self, validated_data):
        contracts = validated_data.pop("contracts", [])
        validated_data["created_by"] = self.context["request"].user
        course = super().create(validated_data)
        if contracts:
            course.contracts.set(contracts)
        return course


class MediaAssetSerializer(serializers.ModelSerializer):
    """Serializer for MediaAsset model."""

    uploaded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = MediaAsset
        fields = [
            "id",
            "filename",
            "original_name",
            "file",
            "file_type",
            "mime_type",
            "size",
            "thumbnail",
            "compressed_file",
            "status",
            "processing_error",
            "duration",
            "metadata",
            "uploaded_by",
            "uploaded_by_name",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "filename",
            "mime_type",
            "size",
            "status",
            "processing_error",
            "uploaded_by",
            "created_at",
        ]

    def get_uploaded_by_name(self, obj):
        return obj.uploaded_by.get_full_name() if obj.uploaded_by else None


class EnrollmentSerializer(serializers.ModelSerializer):
    """Serializer for Enrollment model."""

    user_name = serializers.SerializerMethodField()
    course_title = serializers.SerializerMethodField()

    class Meta:
        model = Enrollment
        fields = [
            "id",
            "user",
            "user_name",
            "course",
            "course_title",
            "status",
            "progress",
            "started_at",
            "completed_at",
            "due_date",
            "assigned_by",
            "created_at",
        ]
        read_only_fields = ["id", "progress", "started_at", "completed_at", "created_at"]

    def get_user_name(self, obj):
        return obj.user.get_full_name()

    def get_course_title(self, obj):
        return obj.course.title


class EnrollmentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating enrollments."""

    class Meta:
        model = Enrollment
        fields = ["user", "course", "due_date"]

    def create(self, validated_data):
        validated_data["assigned_by"] = self.context["request"].user
        return super().create(validated_data)


class BulkEnrollmentSerializer(serializers.Serializer):
    """Serializer for bulk enrollment."""

    user_ids = serializers.ListField(child=serializers.IntegerField())
    course_id = serializers.IntegerField()
    due_date = serializers.DateField(required=False, allow_null=True)


class LessonProgressSerializer(serializers.ModelSerializer):
    """Serializer for LessonProgress model."""

    lesson_title = serializers.SerializerMethodField()

    class Meta:
        model = LessonProgress
        fields = [
            "id",
            "enrollment",
            "lesson",
            "lesson_title",
            "is_completed",
            "progress_percent",
            "time_spent",
            "last_position",
            "completed_at",
        ]
        read_only_fields = ["id", "enrollment", "completed_at"]

    def get_lesson_title(self, obj):
        return obj.lesson.title


class LessonProgressUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating lesson progress."""

    class Meta:
        model = LessonProgress
        fields = ["progress_percent", "time_spent", "last_position", "is_completed"]


class CourseVersionSerializer(serializers.ModelSerializer):
    """Serializer for CourseVersion model."""

    created_by_name = serializers.CharField(source="created_by.get_full_name", read_only=True)

    class Meta:
        model = CourseVersion
        fields = [
            "id",
            "course",
            "version_number",
            "snapshot",
            "changelog",
            "is_major_version",
            "published_at",
            "created_by",
            "created_by_name",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "course",
            "version_number",
            "snapshot",
            "created_by",
            "created_at",
        ]


class CourseVersionCreateSerializer(serializers.Serializer):
    """Serializer for creating course versions."""

    changelog = serializers.CharField(required=False, default="")
    is_major = serializers.BooleanField(required=False, default=False)


class ScormPackageSerializer(serializers.ModelSerializer):
    """Serializer for ScormPackage model."""

    lesson_title = serializers.CharField(source="lesson.title", read_only=True)
    launch_url = serializers.ReadOnlyField()

    class Meta:
        model = ScormPackage
        fields = [
            "id",
            "lesson",
            "lesson_title",
            "package_file",
            "extracted_path",
            "entry_point",
            "scorm_version",
            "status",
            "manifest_data",
            "error_message",
            "file_size",
            "launch_url",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "extracted_path",
            "entry_point",
            "scorm_version",
            "status",
            "manifest_data",
            "error_message",
            "file_size",
            "created_at",
            "updated_at",
        ]


class ScormAttemptSerializer(serializers.ModelSerializer):
    """Serializer for ScormAttempt model."""

    lesson_title = serializers.CharField(source="scorm_package.lesson.title", read_only=True)
    user_name = serializers.CharField(source="enrollment.user.get_full_name", read_only=True)

    class Meta:
        model = ScormAttempt
        fields = [
            "id",
            "enrollment",
            "scorm_package",
            "lesson_title",
            "user_name",
            "attempt_number",
            "lesson_status",
            "score_raw",
            "score_min",
            "score_max",
            "session_time",
            "total_time",
            "suspend_data",
            "location",
            "interactions",
            "started_at",
            "last_accessed_at",
            "completed_at",
        ]
        read_only_fields = ["id", "enrollment", "scorm_package", "attempt_number", "started_at"]


class ScormDataUpdateSerializer(serializers.Serializer):
    """Serializer for updating SCORM data from client."""

    cmi_element = serializers.CharField()
    value = serializers.CharField(allow_blank=True)


class ResourceLibrarySerializer(serializers.ModelSerializer):
    """Serializer for ResourceLibrary model."""

    uploaded_by_name = serializers.CharField(source="uploaded_by.get_full_name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = ResourceLibrary
        fields = [
            "id",
            "name",
            "description",
            "resource_type",
            "file",
            "thumbnail",
            "file_size",
            "mime_type",
            "tags",
            "category",
            "category_name",
            "usage_count",
            "is_public",
            "uploaded_by",
            "uploaded_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "file_size",
            "mime_type",
            "usage_count",
            "uploaded_by",
            "created_at",
            "updated_at",
        ]


class ResourceLibraryCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating library resources."""

    class Meta:
        model = ResourceLibrary
        fields = ["name", "description", "resource_type", "file", "tags", "category"]

    def create(self, validated_data):
        file = validated_data.get("file")
        validated_data["uploaded_by"] = self.context["request"].user
        validated_data["file_size"] = file.size if file else 0

        import mimetypes

        mime_type, _ = mimetypes.guess_type(file.name) if file else (None, None)
        validated_data["mime_type"] = mime_type or "application/octet-stream"

        return super().create(validated_data)


class ResourceLibraryListSerializer(serializers.ModelSerializer):
    """Simplified serializer for resource lists."""

    class Meta:
        model = ResourceLibrary
        fields = [
            "id",
            "name",
            "resource_type",
            "thumbnail",
            "file_size",
            "usage_count",
            "created_at",
        ]
