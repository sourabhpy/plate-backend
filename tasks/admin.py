from django.contrib import admin
from .models import Project, Task, TaskActivity, TaskAttachment


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "workspace", "created_at")
    search_fields = ("name", "workspace__name")


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "workspace", "status", "priority", "assignee", "creator", "created_at")
    list_filter = ("status", "priority", "workspace")
    search_fields = ("title", "description", "workspace__name")


@admin.register(TaskActivity)
class TaskActivityAdmin(admin.ModelAdmin):
    list_display = ("task", "actor", "field_name", "old_value", "new_value", "created_at")
    list_filter = ("field_name",)


@admin.register(TaskAttachment)
class TaskAttachmentAdmin(admin.ModelAdmin):
    list_display = ("file_name", "task", "uploader", "created_at")
