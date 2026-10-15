from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from core.models import User, Workspace, WorkspaceMember
from tasks.models import Task, TaskActivity


class TaskManagementTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin_user = User.objects.create_user(email="admin@corp.com", password="Pass1!", name="Admin")
        self.member_user = User.objects.create_user(email="dev@corp.com", password="Pass2!", name="Dev Alice")
        
        self.workspace = Workspace.objects.create(name="Corp OS", owner=self.admin_user)
        self.admin_member = WorkspaceMember.objects.create(
            workspace=self.workspace, user=self.admin_user, role="admin", status="active"
        )
        self.dev_member = WorkspaceMember.objects.create(
            workspace=self.workspace, user=self.member_user, role="member", status="active"
        )

        self.client.force_authenticate(user=self.admin_user)

    def test_create_and_assign_task(self):
        response = self.client.post("/api/tasks/", {
            "title": "Build dark mode toggle",
            "description": "Minimalist CSS toggle",
            "assignee_id": str(self.dev_member.id),
            "priority": "high",
            "status": "inbox"
        }, format="json", HTTP_X_WORKSPACE_ID=str(self.workspace.id))

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        task_id = response.data["id"]
        
        task = Task.objects.get(id=task_id)
        self.assertEqual(task.assignee, self.dev_member)
        self.assertEqual(task.priority, "high")
        self.assertEqual(task.status, "inbox")

        # Verify activity history was created
        activities = TaskActivity.objects.filter(task=task)
        self.assertTrue(activities.exists())

    def test_task_move_drag_and_drop(self):
        task = Task.objects.create(
            workspace=self.workspace,
            title="Design system cards",
            status="todo",
            assignee=None,
            creator=self.admin_user
        )

        # Move to dev_member and 'in_progress'
        response = self.client.patch(f"/api/tasks/{task.id}/move/", {
            "status": "in_progress",
            "assignee_id": str(self.dev_member.id),
            "position": 2
        }, format="json", HTTP_X_WORKSPACE_ID=str(self.workspace.id))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        task.refresh_from_db()
        self.assertEqual(task.status, "in_progress")
        self.assertEqual(task.assignee, self.dev_member)
        self.assertEqual(task.position, 2)

        # Verify logged activities
        act = TaskActivity.objects.filter(task=task, field_name="status").first()
        self.assertIsNotNone(act)
        self.assertEqual(act.new_value, "in_progress")

    def test_task_attachment_size_limit(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        task = Task.objects.create(
            workspace=self.workspace,
            title="Attachment size test",
            status="todo",
            creator=self.admin_user,
        )

        # 6MB file should be rejected
        oversized = SimpleUploadedFile("big_file.pdf", b"X" * (6 * 1024 * 1024), content_type="application/pdf")
        res = self.client.post(
            f"/api/tasks/{task.id}/attachments/",
            {"file": oversized},
            format="multipart",
            HTTP_X_WORKSPACE_ID=str(self.workspace.id),
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("5MB", res.data["error"])

        # 1MB file should be accepted
        valid_file = SimpleUploadedFile("valid.pdf", b"X" * (1024 * 1024), content_type="application/pdf")
        res_ok = self.client.post(
            f"/api/tasks/{task.id}/attachments/",
            {"file": valid_file},
            format="multipart",
            HTTP_X_WORKSPACE_ID=str(self.workspace.id),
        )
        self.assertEqual(res_ok.status_code, status.HTTP_201_CREATED)

    def test_task_attachment_rejects_video_file(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        task = Task.objects.create(
            workspace=self.workspace,
            title="Video attachment test",
            status="todo",
            creator=self.admin_user,
        )

        video_file = SimpleUploadedFile("clip.mp4", b"fake mp4 video bytes", content_type="video/mp4")
        res = self.client.post(
            f"/api/tasks/{task.id}/attachments/",
            {"file": video_file},
            format="multipart",
            HTTP_X_WORKSPACE_ID=str(self.workspace.id),
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Video files are not allowed", res.data["error"])

