from django.db import models
from django.utils import timezone
import uuid
from core.models import Workspace, User


class Conversation(models.Model):
    TYPE_CHOICES = [
        ("channel", "Channel"),
        ("dm", "Direct Message"),
        ("group", "Private Group"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="conversations")
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default="channel")
    name = models.CharField(max_length=255, blank=True, default="")
    topic = models.CharField(max_length=500, blank=True, default="")
    is_private = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="created_conversations")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        if self.type == "channel":
            return f"#{self.name} ({self.workspace.name})"
        return f"{self.type}:{self.id} ({self.workspace.name})"


class ConversationMember(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="conversation_memberships")
    last_read_message_id = models.BigIntegerField(default=0)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("conversation", "user")

    def __str__(self):
        return f"{self.user.name} in {self.conversation}"


class Message(models.Model):
    MESSAGE_TYPES = [
        ("text", "Text"),
        ("audio", "Audio Voice Message"),
        ("file", "File Attachment"),
    ]

    id = models.BigAutoField(primary_key=True)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sent_messages")
    parent_message = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="replies"
    )
    message_type = models.CharField(max_length=20, choices=MESSAGE_TYPES, default="text")
    content = models.TextField(blank=True, default="")
    
    # Audio message fields
    audio_file = models.FileField(upload_to="audio_messages/", null=True, blank=True)
    audio_duration = models.FloatField(default=0.0)
    
    # File attachment fields
    file = models.FileField(upload_to="message_attachments/", null=True, blank=True)
    file_name = models.CharField(max_length=255, blank=True, default="")
    file_size = models.IntegerField(default=0)
    content_type = models.CharField(max_length=100, blank=True, default="")

    is_edited = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]
        indexes = [
            models.Index(fields=["conversation", "id"]),
            models.Index(fields=["conversation", "created_at"]),
            models.Index(fields=["conversation", "parent_message", "id"]),
        ]

    def __str__(self):
        return f"Msg {self.id} by {self.sender.name} in {self.conversation.id}"
