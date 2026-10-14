from rest_framework import serializers
from .models import Project, Task, TaskActivity, TaskAttachment
from core.serializers import WorkspaceMemberSerializer, UserSerializer


class ProjectSerializer(serializers.ModelSerializer):
    task_count = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = ["id", "workspace", "name", "description", "task_count", "created_at"]
        read_only_fields = ["id", "workspace", "created_at"]

    def get_task_count(self, obj):
        return obj.tasks.count()


class TaskAttachmentSerializer(serializers.ModelSerializer):
    uploader = UserSerializer(read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = TaskAttachment
        fields = ["id", "task", "uploader", "file", "file_name", "file_size", "content_type", "file_url", "created_at"]
        read_only_fields = ["id", "task", "uploader", "file_size", "content_type", "created_at"]

    def get_file_url(self, obj):
        request = self.context.get("request")
        if obj.file and hasattr(obj.file, "url"):
            return request.build_absolute_uri(obj.file.url) if request else obj.file.url
        return None


class TaskActivitySerializer(serializers.ModelSerializer):
    actor = UserSerializer(read_only=True)

    class Meta:
        model = TaskActivity
        fields = ["id", "task", "actor", "field_name", "old_value", "new_value", "description", "created_at"]
        read_only_fields = ["id", "task", "actor", "created_at"]


class TaskSerializer(serializers.ModelSerializer):
    assignee = WorkspaceMemberSerializer(read_only=True)
    assignee_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)
    creator = UserSerializer(read_only=True)
    attachments = TaskAttachmentSerializer(many=True, read_only=True)
    activities = TaskActivitySerializer(many=True, read_only=True)
    project_name = serializers.CharField(source="project.name", read_only=True)

    class Meta:
        model = Task
        fields = [
            "id",
            "workspace",
            "project",
            "project_name",
            "title",
            "description",
            "assignee",
            "assignee_id",
            "creator",
            "status",
            "priority",
            "deadline",
            "labels",
            "source_type",
            "source_id",
            "evidence_quote",
            "position",
            "attachments",
            "activities",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "workspace", "creator", "created_at", "updated_at"]
