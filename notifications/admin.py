from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "workspace", "recipient", "actor", "notification_type", "is_read", "created_at")
    list_filter = ("notification_type", "is_read", "workspace")
    search_fields = ("title", "message", "recipient__email", "recipient__username")
