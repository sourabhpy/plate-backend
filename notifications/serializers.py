from rest_framework import serializers
from .models import Notification
from core.serializers import UserSerializer


class NotificationSerializer(serializers.ModelSerializer):
    actor = UserSerializer(read_only=True)
    task_id = serializers.UUIDField(source="task.id", read_only=True)
    task_title = serializers.CharField(source="task.title", read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id",
            "workspace",
            "recipient",
            "actor",
            "task",
            "task_id",
            "task_title",
            "notification_type",
            "title",
            "message",
            "is_read",
            "created_at",
        ]
        read_only_fields = ["id", "workspace", "recipient", "created_at"]
