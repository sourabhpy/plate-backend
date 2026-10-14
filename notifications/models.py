from django.db import models
import uuid
from core.models import Workspace, User


class Notification(models.Model):
    TYPE_CHOICES = [
        ("task_assigned", "Task Assigned"),
        ("task_reassigned", "Task Reassigned"),
        ("deadline_changed", "Deadline Changed"),
        ("priority_changed", "Priority Changed"),
        ("mention", "Mention"),
        ("system", "System"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="notifications")
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    task = models.ForeignKey("tasks.Task", on_delete=models.CASCADE, null=True, blank=True)
    notification_type = models.CharField(max_length=50, choices=TYPE_CHOICES, default="system")
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Notification to {self.recipient.email}: {self.title}"
