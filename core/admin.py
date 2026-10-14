from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Workspace, WorkspaceMember


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "name", "is_staff", "is_superuser", "is_active")
    search_fields = ("username", "email", "name")
    list_filter = ("is_staff", "is_superuser", "is_active")
    ordering = ("username",)
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal info", {"fields": ("name", "email", "avatar")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "email", "name", "password"),
            },
        ),
    )


@admin.register(Workspace)
class WorkspaceAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "owner", "created_at")
    search_fields = ("name", "slug", "owner__email", "owner__username")
    ordering = ("-created_at",)


@admin.register(WorkspaceMember)
class WorkspaceMemberAdmin(admin.ModelAdmin):
    list_display = ("workspace", "user", "role", "title", "status", "joined_at")
    list_filter = ("role", "status")
    search_fields = ("workspace__name", "user__email", "user__username", "user__name")
