from rest_framework import serializers
from .models import Conversation, ConversationMember, Message
from core.serializers import UserSerializer


class MessageSerializer(serializers.ModelSerializer):
    sender = UserSerializer(read_only=True)
    audio_url = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()
    reply_count = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            "id",
            "conversation",
            "sender",
            "parent_message",
            "message_type",
            "content",
            "audio_file",
            "audio_url",
            "audio_duration",
            "file",
            "file_url",
            "file_name",
            "file_size",
            "content_type",
            "is_edited",
            "reply_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "sender",
            "audio_url",
            "file_url",
            "is_edited",
            "reply_count",
            "created_at",
            "updated_at",
        ]

    def get_audio_url(self, obj):
        request = self.context.get("request")
        if obj.audio_file and hasattr(obj.audio_file, "url"):
            return request.build_absolute_uri(obj.audio_file.url) if request else obj.audio_file.url
        return None

    def get_file_url(self, obj):
        request = self.context.get("request")
        if obj.file and hasattr(obj.file, "url"):
            return request.build_absolute_uri(obj.file.url) if request else obj.file.url
        return None

    def get_reply_count(self, obj):
        if obj.parent_message_id is None:
            return obj.replies.count()
        return 0


class ConversationSerializer(serializers.ModelSerializer):
    members = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            "id",
            "workspace",
            "type",
            "name",
            "topic",
            "is_private",
            "members",
            "display_name",
            "last_message",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "workspace", "created_at", "updated_at"]

    def get_members(self, obj):
        memberships = obj.members.select_related("user")
        return [UserSerializer(m.user).data for m in memberships]

    def get_display_name(self, obj):
        if obj.type == "channel":
            return f"#{obj.name}"
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            other_members = [
                m.user.name for m in obj.members.select_related("user") if m.user != request.user
            ]
            if other_members:
                return ", ".join(other_members)
        return obj.name or "Conversation"

    def get_last_message(self, obj):
        msg = obj.messages.filter(parent_message__isnull=True).order_by("-id").first()
        if msg:
            return {
                "id": msg.id,
                "sender_name": msg.sender.name,
                "content": msg.content or ("[Voice Message]" if msg.message_type == "audio" else "[Attachment]"),
                "message_type": msg.message_type,
                "created_at": msg.created_at,
            }
        return None
