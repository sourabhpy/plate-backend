from django.db import models
from django.utils import timezone
import uuid
from core.models import Workspace, WorkspaceMember, User


class Project(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="projects")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.workspace.name})"


class Task(models.Model):
    STATUS_CHOICES = [
        ("inbox", "Inbox"),
        ("todo", "To Do"),
        ("in_progress", "In Progress"),
        ("in_review", "In Review"),
        ("done", "Done"),
    ]
    PRIORITY_CHOICES = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("urgent", "Urgent"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="tasks")
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name="tasks")
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    assignee = models.ForeignKey(
        WorkspaceMember,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_tasks"
    )
    creator = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_tasks"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="inbox")
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default="medium")
    deadline = models.DateTimeField(null=True, blank=True)
    labels = models.JSONField(default=list, blank=True)
    
    # Source Reference (voice note, chat message, document, or manual)
    source_type = models.CharField(max_length=50, blank=True, default="manual")
    source_id = models.CharField(max_length=255, blank=True, default="")
    evidence_quote = models.TextField(blank=True, default="")

    position = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["position", "-created_at"]

    def __str__(self):
        return f"[{self.status}] {self.title}"


class TaskActivity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="activities")
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="task_actions")
    field_name = models.CharField(max_length=100)
    old_value = models.TextField(blank=True, default="")
    new_value = models.TextField(blank=True, default="")
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.actor} changed {self.field_name} on {self.task.title}"


class TaskAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="attachments")
    uploader = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    file = models.FileField(upload_to="task_attachments/")
    file_name = models.CharField(max_length=255)
    file_size = models.IntegerField(default=0)
    content_type = models.CharField(max_length=100, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.file_name
