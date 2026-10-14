from django.urls import path
from .views import (
    TaskListCreateView,
    TaskDetailView,
    TaskMoveView,
    TaskAttachmentUploadView,
    ProjectListCreateView,
)

urlpatterns = [
    path("", TaskListCreateView.as_view(), name="task-list-create"),
    path("<uuid:pk>/", TaskDetailView.as_view(), name="task-detail"),
    path("<uuid:pk>/move/", TaskMoveView.as_view(), name="task-move"),
    path("<uuid:pk>/attachments/", TaskAttachmentUploadView.as_view(), name="task-attachment-upload"),
    path("projects/", ProjectListCreateView.as_view(), name="project-list-create"),
]
