from rest_framework import permissions
from .models import WorkspaceMember, Workspace


class IsWorkspaceMember(permissions.BasePermission):
    """
    Ensures that the authenticated user is an active member of the workspace.
    Resolves the workspace from 'X-Workspace-ID' header or 'workspace_id' query/body parameter.
    Attaches `request.workspace` and `request.member` to the request.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        workspace_id = (
            request.headers.get("X-Workspace-ID")
            or request.query_params.get("workspace_id")
            or (request.data.get("workspace_id") if hasattr(request, "data") and isinstance(request.data, dict) else None)
        )

        if not workspace_id:
            # If view doesn't specify a workspace ID in headers, check if user has memberships
            # For general endpoints, we allow it if the user has any active membership
            first_membership = WorkspaceMember.objects.filter(user=request.user, status="active").first()
            if first_membership:
                request.workspace = first_membership.workspace
                request.member = first_membership
                return True
            return False

        try:
            member = WorkspaceMember.objects.select_related("workspace", "user").get(
                workspace_id=workspace_id,
                user=request.user,
                status="active"
            )
            request.workspace = member.workspace
            request.member = member
            return True
        except (WorkspaceMember.DoesNotExist, ValueError):
            return False


class IsWorkspaceAdmin(IsWorkspaceMember):
    """
    Ensures the user is an active admin of the specified workspace.
    """
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return getattr(request, "member", None) and request.member.role == "admin"
