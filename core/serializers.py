from rest_framework import serializers
from .models import User, Workspace, WorkspaceMember


class UserSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "email", "name", "avatar", "avatar_url", "date_joined"]
        read_only_fields = ["id", "email", "date_joined"]

    def get_avatar_url(self, obj):
        if not obj.avatar:
            return None
        request = self.context.get("request")
        if request:
            try:
                return request.build_absolute_uri(obj.avatar.url)
            except Exception:
                pass
        return obj.avatar.url



class RegisterSerializer(serializers.ModelSerializer):
    username = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, min_length=6)
    workspace_name = serializers.CharField(write_only=True, required=False, default="My Workspace")

    class Meta:
        model = User
        fields = ["username", "email", "name", "password", "workspace_name"]

    def create(self, validated_data):
        workspace_name = validated_data.pop("workspace_name", "My Workspace")
        password = validated_data.pop("password")
        username = validated_data.pop("username", None)
        if username:
            user = User.objects.create_user(username=username, password=password, **validated_data)
        else:
            user = User.objects.create_user(password=password, **validated_data)

        # Create initial workspace for the user and make them admin
        workspace = Workspace.objects.create(name=workspace_name, owner=user)
        WorkspaceMember.objects.create(
            workspace=workspace,
            user=user,
            role="admin",
            title="Founder & Admin",
            status="active"
        )
        return user


class WorkspaceSerializer(serializers.ModelSerializer):
    member_count = serializers.SerializerMethodField()
    my_role = serializers.SerializerMethodField()

    class Meta:
        model = Workspace
        fields = ["id", "name", "slug", "owner", "member_count", "my_role", "created_at"]
        read_only_fields = ["id", "slug", "owner", "created_at"]

    def get_member_count(self, obj):
        return obj.members.filter(status="active").count()

    def get_my_role(self, obj):
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            member = obj.members.filter(user=request.user).first()
            return member.role if member else None
        return None


class WorkspaceMemberSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = WorkspaceMember
        fields = ["id", "workspace", "user", "role", "title", "status", "joined_at"]
        read_only_fields = ["id", "workspace", "joined_at"]


class InviteMemberSerializer(serializers.Serializer):
    email = serializers.EmailField()
    name = serializers.CharField(required=False, default="")
    password = serializers.CharField(required=False, allow_blank=True, min_length=6)
    role = serializers.ChoiceField(choices=["admin", "member"], default="member")
    title = serializers.CharField(required=False, default="Team Member")
    avatar = serializers.ImageField(required=False, allow_null=True)

