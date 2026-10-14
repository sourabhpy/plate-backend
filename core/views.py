from rest_framework import status, views, permissions
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
                    "user": UserSerializer(user).data,
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
                "user": UserSerializer(user).data,
                "tokens": tokens,
                "workspaces": WorkspaceSerializer(workspaces, many=True, context={"request": request}).data,
                "active_workspace": WorkspaceSerializer(active_workspace, context={"request": request}).data if active_workspace else None,
            },
            status=status.HTTP_200_OK,
        )


class MeView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

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
                "user": UserSerializer(request.user).data,
                "workspaces": WorkspaceSerializer(workspaces, many=True, context={"request": request}).data,
                "active_member": WorkspaceMemberSerializer(active_member).data if active_member else None,
            }
        )


class WorkspaceListView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        memberships = WorkspaceMember.objects.filter(user=request.user, status="active").select_related("workspace")
        workspaces = [m.workspace for m in memberships]
        return Response(WorkspaceSerializer(workspaces, many=True, context={"request": request}).data)

    def post(self, request):
        name = request.data.get("name")
        if not name:
            return Response({"error": "Workspace name is required"}, status=status.HTTP_400_BAD_REQUEST)

        workspace = Workspace.objects.create(name=name, owner=request.user)
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
            workspace.name = name
            workspace.save()
        return Response(WorkspaceSerializer(workspace, context={"request": request}).data)


class WorkspaceMembersView(views.APIView):
    permission_classes = [IsWorkspaceMember]

    def get(self, request):
        members = WorkspaceMember.objects.filter(
            workspace=request.workspace, status="active"
        ).select_related("user").order_by("joined_at")
        return Response(WorkspaceMemberSerializer(members, many=True).data)

    def post(self, request):
        if request.member.role != "admin":
            return Response({"error": "Only admins can invite members"}, status=status.HTTP_403_FORBIDDEN)

        serializer = InviteMemberSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        email = serializer.validated_data["email"].lower().strip()
        name = serializer.validated_data.get("name") or email.split("@")[0]
        role = serializer.validated_data.get("role", "member")
        title = serializer.validated_data.get("title", "Team Member")

        user, created = User.objects.get_or_create(
            email=email,
            defaults={"name": name}
        )
        if created:
            user.set_password("Plate123!")
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

        return Response(WorkspaceMemberSerializer(member).data, status=status.HTTP_201_CREATED)
