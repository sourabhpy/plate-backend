from django.contrib import admin
from .models import Conversation, ConversationMember, Message


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("name", "workspace", "type", "is_private", "created_by", "created_at")
    list_filter = ("type", "is_private")
    search_fields = ("name", "workspace__name")


@admin.register(ConversationMember)
class ConversationMemberAdmin(admin.ModelAdmin):
    list_display = ("conversation", "user", "joined_at")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "sender", "content", "created_at")
    search_fields = ("content", "sender__email", "sender__username")
    ordering = ("-id",)
