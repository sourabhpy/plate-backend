from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from .models import User, Workspace, WorkspaceMember


class CoreAuthAndWorkspaceTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_register_creates_user_and_workspace(self):
        response = self.client.post("/api/auth/register/", {
            "email": "sarah@acme.com",
            "name": "Sarah Connor",
            "password": "SecurePassword123!",
            "workspace_name": "Acme Robotics"
        }, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("tokens", response.data)
        self.assertIn("access", response.data["tokens"])
        self.assertIn("workspace", response.data)
        self.assertEqual(response.data["workspace"]["name"], "Acme Robotics")

        # Verify database
        user = User.objects.get(email="sarah@acme.com")
        self.assertTrue(user.check_password("SecurePassword123!"))
        member = WorkspaceMember.objects.get(user=user)
        self.assertEqual(member.role, "admin")

    def test_login_flow(self):
        user = User.objects.create_user(email="john@acme.com", password="Password123!", name="John")
        workspace = Workspace.objects.create(name="Acme", owner=user)
        WorkspaceMember.objects.create(workspace=workspace, user=user, role="admin", status="active")

        response = self.client.post("/api/auth/login/", {
            "email": "john@acme.com",
            "password": "Password123!"
        }, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("tokens", response.data)
        self.assertIn("access", response.data["tokens"])
        self.assertEqual(response.data["user"]["email"], "john@acme.com")

    def test_workspace_isolation_and_unauthorized_access(self):
        # User 1 with Workspace 1
        u1 = User.objects.create_user(email="u1@test.com", password="Pass1!", name="U1")
        w1 = Workspace.objects.create(name="W1", owner=u1)
        WorkspaceMember.objects.create(workspace=w1, user=u1, role="admin", status="active")

        # User 2 with Workspace 2
        u2 = User.objects.create_user(email="u2@test.com", password="Pass2!", name="U2")
        w2 = Workspace.objects.create(name="W2", owner=u2)
        WorkspaceMember.objects.create(workspace=w2, user=u2, role="admin", status="active")

        # Authenticate as U1
        self.client.force_authenticate(user=u1)

        # Trying to access W2 with header for W2
        response = self.client.get(f"/api/auth/workspaces/{w2.id}/", HTTP_X_WORKSPACE_ID=str(w2.id))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
