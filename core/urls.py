from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    RegisterView,
    LoginView,
    MeView,
    WorkspaceListView,
    WorkspaceDetailView,
    WorkspaceMembersView,
    WorkspaceMemberDetailView,
    SystemUsersView,
)

urlpatterns = [
    path("register/", RegisterView.as_view(), name="auth-register"),
    path("login/", LoginView.as_view(), name="auth-login"),
    path("refresh/", TokenRefreshView.as_view(), name="auth-refresh"),
    path("me/", MeView.as_view(), name="auth-me"),
    path("users/", SystemUsersView.as_view(), name="system-users"),
    path("workspaces/", WorkspaceListView.as_view(), name="workspaces-list"),
    path("workspaces/<uuid:pk>/", WorkspaceDetailView.as_view(), name="workspace-detail"),
    path("members/", WorkspaceMembersView.as_view(), name="workspace-members"),
    path("members/<uuid:pk>/", WorkspaceMemberDetailView.as_view(), name="workspace-member-detail"),
]

