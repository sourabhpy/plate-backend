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

    def test_admin_privileges_workspace_creation(self):
        admin_user = User.objects.create_user(email="admin@test.com", password="PassAdmin1!", name="Admin")
        ws = Workspace.objects.create(name="Team Alpha", owner=admin_user)
        WorkspaceMember.objects.create(workspace=ws, user=admin_user, role="admin", status="active")

        member_user = User.objects.create_user(email="member@test.com", password="PassMember1!", name="Member")
        WorkspaceMember.objects.create(workspace=ws, user=member_user, role="member", status="active")

        # Member tries to create workspace -> 403 Forbidden
        self.client.force_authenticate(user=member_user)
        res = self.client.post("/api/auth/workspaces/", {"name": "Disallowed WS"}, HTTP_X_WORKSPACE_ID=str(ws.id))
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Admin tries to create workspace -> 201 Created
        self.client.force_authenticate(user=admin_user)
        res = self.client.post("/api/auth/workspaces/", {"name": "New Admin WS"}, HTTP_X_WORKSPACE_ID=str(ws.id))
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["name"], "New Admin WS")

    def test_admin_add_new_user_in_workspace(self):
        admin_user = User.objects.create_user(email="admin2@test.com", password="PassAdmin1!", name="Admin 2")
        ws = Workspace.objects.create(name="Dev Studio", owner=admin_user)
        WorkspaceMember.objects.create(workspace=ws, user=admin_user, role="admin", status="active")

        member_user = User.objects.create_user(email="member2@test.com", password="PassMember1!", name="Member 2")
        WorkspaceMember.objects.create(workspace=ws, user=member_user, role="member", status="active")

        # Member tries to add user -> 403
        self.client.force_authenticate(user=member_user)
        res = self.client.post(
            "/api/auth/members/",
            {"name": "New Guy", "email": "newguy@test.com", "password": "NewGuyPassword123!", "role": "member"},
            HTTP_X_WORKSPACE_ID=str(ws.id),
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Admin adds user -> 201
        self.client.force_authenticate(user=admin_user)
        res = self.client.post(
            "/api/auth/members/",
            {"name": "New Guy", "email": "newguy@test.com", "password": "NewGuyPassword123!", "role": "member"},
            HTTP_X_WORKSPACE_ID=str(ws.id),
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        created_user = User.objects.get(email="newguy@test.com")
        self.assertEqual(created_user.name, "New Guy")
        self.assertTrue(created_user.check_password("NewGuyPassword123!"))
        self.assertTrue(WorkspaceMember.objects.filter(workspace=ws, user=created_user, role="member").exists())

    def test_profile_update_and_email_immutability(self):
        user = User.objects.create_user(email="profile_user@test.com", password="OldPassword123!", name="Old Name")
        self.client.force_authenticate(user=user)

        # Attempt to change email should fail
        res = self.client.patch("/api/auth/me/", {"email": "different@test.com", "name": "New Name"})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        user.refresh_from_db()
        self.assertEqual(user.email, "profile_user@test.com")

        # Valid profile update: update name and password
        res = self.client.patch("/api/auth/me/", {
            "name": "Updated Name",
            "current_password": "OldPassword123!",
            "password": "BrandNewPassword123!",
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertEqual(user.name, "Updated Name")
        self.assertTrue(user.check_password("BrandNewPassword123!"))

    def test_system_users_and_workspace_member_management(self):
        admin = User.objects.create_user(email="owner@test.com", password="Pass123!", name="Owner")
        ws = Workspace.objects.create(name="Design Studio", owner=admin)
        WorkspaceMember.objects.create(workspace=ws, user=admin, role="admin", status="active")

        # Two existing system users not yet in this workspace
        user_a = User.objects.create_user(email="user_a@test.com", password="Pass123!", name="User A")
        user_b = User.objects.create_user(email="user_b@test.com", password="Pass123!", name="User B")

        self.client.force_authenticate(user=admin)

        # 1. List system users with workspace context
        res = self.client.get("/api/auth/users/", HTTP_X_WORKSPACE_ID=str(ws.id))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        user_ids_in_res = [u["id"] for u in res.data]
        self.assertIn(str(user_a.id), user_ids_in_res)
        # Verify is_in_workspace flag
        admin_item = next(u for u in res.data if u["id"] == str(admin.id))
        self.assertTrue(admin_item["is_in_workspace"])
        user_a_item = next(u for u in res.data if u["id"] == str(user_a.id))
        self.assertFalse(user_a_item["is_in_workspace"])

        # 2. Admin includes existing user_a into workspace
        res = self.client.post(
            "/api/auth/members/",
            {"user_id": str(user_a.id), "role": "member", "title": "Senior Designer"},
            HTTP_X_WORKSPACE_ID=str(ws.id),
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(WorkspaceMember.objects.filter(workspace=ws, user=user_a).exists())

        # 3. Admin bulk includes user_b into workspace
        res = self.client.post(
            "/api/auth/members/",
            {"user_ids": [str(user_b.id)]},
            format="json",
            HTTP_X_WORKSPACE_ID=str(ws.id),
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(WorkspaceMember.objects.filter(workspace=ws, user=user_b).exists())

        # 4. Admin removes user_a from workspace
        member_a = WorkspaceMember.objects.get(workspace=ws, user=user_a)
        res = self.client.delete(f"/api/auth/members/{member_a.id}/", HTTP_X_WORKSPACE_ID=str(ws.id))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(WorkspaceMember.objects.filter(workspace=ws, user=user_a).exists())

        # 5. Non-admin cannot remove members
        self.client.force_authenticate(user=user_b)
        member_b = WorkspaceMember.objects.get(workspace=ws, user=user_b)
        res = self.client.delete(f"/api/auth/members/{member_b.id}/", HTTP_X_WORKSPACE_ID=str(ws.id))
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


