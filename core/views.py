from rest_framework import status, views, permissions
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.shortcuts import get_object_or_404
from .models import User, Workspace, WorkspaceMember
from .serializers import (
    UserSerializer,
    RegisterSerializer,
    WorkspaceSerializer,
    WorkspaceMemberSerializer,
    InviteMemberSerializer,
)
from .permissions import IsWorkspaceMember, IsWorkspaceAdmin


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }


class RegisterView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            tokens = get_tokens_for_user(user)
            membership = WorkspaceMember.objects.filter(user=user).select_related("workspace").first()
            return Response(
                {
                    "user": UserSerializer(user, context={"request": request}).data,
                    "tokens": tokens,
                    "workspace": WorkspaceSerializer(membership.workspace, context={"request": request}).data if membership else None,
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        identifier = request.data.get("email") or request.data.get("username")
        password = request.data.get("password")

        if not identifier or not password:
            return Response(
                {"error": "Username or email and password are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(request, username=identifier, password=password)
        if not user:
            return Response(
                {"error": "Invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        tokens = get_tokens_for_user(user)
        memberships = WorkspaceMember.objects.filter(user=user, status="active").select_related("workspace")
        workspaces = [m.workspace for m in memberships]

        active_workspace = workspaces[0] if workspaces else None

        return Response(
            {
                "user": UserSerializer(user, context={"request": request}).data,
                "tokens": tokens,
                "workspaces": WorkspaceSerializer(workspaces, many=True, context={"request": request}).data,
                "active_workspace": WorkspaceSerializer(active_workspace, context={"request": request}).data if active_workspace else None,
            },
            status=status.HTTP_200_OK,
        )


class MeView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        memberships = WorkspaceMember.objects.filter(user=request.user, status="active").select_related("workspace")
        workspaces = [m.workspace for m in memberships]

        workspace_id = request.headers.get("X-Workspace-ID")
        active_member = None
        if workspace_id:
            active_member = memberships.filter(workspace_id=workspace_id).first()
        if not active_member and memberships.exists():
            active_member = memberships.first()

        return Response(
            {
                "user": UserSerializer(request.user, context={"request": request}).data,
                "workspaces": WorkspaceSerializer(workspaces, many=True, context={"request": request}).data,
                "active_member": WorkspaceMemberSerializer(active_member, context={"request": request}).data if active_member else None,
            }
        )

    def patch(self, request):
        user = request.user

        # Email cannot be changed as it is a primary value
        requested_email = request.data.get("email")
        if requested_email and requested_email.strip().lower() != user.email.lower():
            return Response(
                {"error": "Email cannot be changed as it is a primary identifier."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        name = request.data.get("name")
        if name is not None:
            user.name = name.strip()

        # Handle avatar upload or removal
        if "avatar" in request.FILES:
            user.avatar = request.FILES["avatar"]
        elif str(request.data.get("remove_avatar")).lower() in ["true", "1", "yes"]:
            if user.avatar:
                user.avatar.delete(save=False)
            user.avatar = None

        # Handle password update
        new_password = request.data.get("password") or request.data.get("new_password")
        if new_password:
            if len(new_password) < 6:
                return Response(
                    {"error": "New password must be at least 6 characters long."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            current_password = request.data.get("current_password")
            if current_password:
                if not user.check_password(current_password):
                    return Response(
                        {"error": "Current password is incorrect."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            user.set_password(new_password)

        user.save()

        return Response(
            {
                "user": UserSerializer(user, context={"request": request}).data,
                "message": "Profile updated successfully",
            },
            status=status.HTTP_200_OK,
        )


class WorkspaceListView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        memberships = WorkspaceMember.objects.filter(user=request.user, status="active").select_related("workspace")
        workspaces = [m.workspace for m in memberships]
        return Response(WorkspaceSerializer(workspaces, many=True, context={"request": request}).data)

    def post(self, request):
        # Enforce admin privilege: user must be an admin of their active workspace or an admin in at least one workspace / staff
        active_ws_id = request.headers.get("X-Workspace-ID")
        if active_ws_id:
            is_admin = WorkspaceMember.objects.filter(
                workspace_id=active_ws_id, user=request.user, role="admin", status="active"
            ).exists()
        else:
            is_admin = WorkspaceMember.objects.filter(
                user=request.user, role="admin", status="active"
            ).exists() or request.user.is_staff or request.user.is_superuser

        if not is_admin:
            return Response(
                {"error": "Only admins have permission to create workspaces."},
                status=status.HTTP_403_FORBIDDEN,
            )

        name = request.data.get("name")
        if not name or not name.strip():
            return Response({"error": "Workspace name is required"}, status=status.HTTP_400_BAD_REQUEST)

        workspace = Workspace.objects.create(name=name.strip(), owner=request.user)
        WorkspaceMember.objects.create(
            workspace=workspace,
            user=request.user,
            role="admin",
            title="Founder",
            status="active",
        )
        return Response(
            WorkspaceSerializer(workspace, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class WorkspaceDetailView(views.APIView):
    permission_classes = [IsWorkspaceMember]

    def get(self, request, pk):
        workspace = get_object_or_404(Workspace, pk=pk)
        return Response(WorkspaceSerializer(workspace, context={"request": request}).data)

    def patch(self, request, pk):
        if request.member.role != "admin":
            return Response({"error": "Only admins can edit workspace settings"}, status=status.HTTP_403_FORBIDDEN)
        workspace = get_object_or_404(Workspace, pk=pk)
        name = request.data.get("name")
        if name:
            workspace.name = name.strip()
            workspace.save()
        return Response(WorkspaceSerializer(workspace, context={"request": request}).data)


class WorkspaceMembersView(views.APIView):
    permission_classes = [IsWorkspaceMember]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        members = WorkspaceMember.objects.filter(
            workspace=request.workspace, status="active"
        ).select_related("user").order_by("joined_at")
        return Response(WorkspaceMemberSerializer(members, many=True, context={"request": request}).data)

    def post(self, request):
        if request.member.role != "admin":
            return Response({"error": "Only admins can add members to this workspace"}, status=status.HTTP_403_FORBIDDEN)

        serializer = InviteMemberSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data["email"].lower().strip()
        name = serializer.validated_data.get("name", "").strip() or email.split("@")[0]
        role = serializer.validated_data.get("role", "member")
        title = serializer.validated_data.get("title", "Team Member")
        password = serializer.validated_data.get("password") or request.data.get("password")
        avatar_file = request.FILES.get("avatar")

        if not password or len(password) < 6:
            return Response(
                {"error": "Password is required and must be at least 6 characters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User.objects.filter(email=email).first()
        if user:
            if name:
                user.name = name
            user.set_password(password)
            if avatar_file:
                user.avatar = avatar_file
            user.save()
        else:
            user = User.objects.create_user(
                email=email,
                name=name,
                password=password,
            )
            if avatar_file:
                user.avatar = avatar_file
                user.save()

        member, member_created = WorkspaceMember.objects.get_or_create(
            workspace=request.workspace,
            user=user,
            defaults={
                "role": role,
                "title": title,
                "status": "active",
            }
        )
        if not member_created:
            member.role = role
            member.title = title
            member.status = "active"
            member.save()

        return Response(WorkspaceMemberSerializer(member, context={"request": request}).data, status=status.HTTP_201_CREATED)

