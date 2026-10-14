from django.db import models
import uuid
from core.models import Workspace, User


class TeamMemoryChunk(models.Model):
    SOURCE_TYPES = [
        ("message", "Chat Message"),
        ("voice_note", "Voice Transcript"),
        ("task", "Task Record"),
        ("document", "Document Analysis"),
        ("decision", "Decision"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="memory_chunks")
    source_type = models.CharField(max_length=50, choices=SOURCE_TYPES)
    source_id = models.CharField(max_length=255)
    title = models.CharField(max_length=255)
    content = models.TextField()
    embedding = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["workspace", "source_type"]),
            models.Index(fields=["workspace", "source_id"]),
        ]

    def __str__(self):
        return f"[{self.source_type}] {self.title} ({self.workspace.name})"


class DocumentAnalysis(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="document_analyses")
    file = models.FileField(upload_to="document_analyses/")
    file_name = models.CharField(max_length=255)
    file_type = models.CharField(max_length=50)
    extracted_text = models.TextField(blank=True, default="")
    summary = models.TextField(blank=True, default="")
    key_findings = models.JSONField(default=list, blank=True)
    issues = models.JSONField(default=list, blank=True)
    suggested_tasks = models.JSONField(default=list, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Analysis of {self.file_name}"


class VoiceExtraction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="voice_extractions")
    audio_file = models.FileField(upload_to="voice_extractions/", null=True, blank=True)
    transcript = models.TextField(blank=True, default="")
    decisions = models.JSONField(default=list, blank=True)
    blockers = models.JSONField(default=list, blank=True)
    extracted_tasks = models.JSONField(default=list, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Voice Extraction {self.id} ({self.created_at})"
