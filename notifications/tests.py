from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from core.models import User, Workspace, WorkspaceMember
from notifications.models import Notification


class NotificationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(email="notif_user@example.com", password="Password123!", name="Notif User")
        self.actor = User.objects.create_user(email="sender@example.com", password="Password123!", name="Sender User")
        self.workspace = Workspace.objects.create(name="Notification Workspace", owner=self.user)
        self.member = WorkspaceMember.objects.create(workspace=self.workspace, user=self.user, role="member")
        self.client.force_authenticate(user=self.user)
        self.headers = {"HTTP_X_WORKSPACE_ID": str(self.workspace.id)}

    def test_list_notifications_and_unread_count(self):
        Notification.objects.create(
            workspace=self.workspace,
            recipient=self.user,
            actor=self.actor,
            notification_type="task_assigned",
            title="Task Assigned",
            message="You were assigned a new task.",
            is_read=False,
        )
        Notification.objects.create(
            workspace=self.workspace,
            recipient=self.user,
            actor=self.actor,
            notification_type="priority_changed",
            title="Priority Changed",
            message="Task priority changed to high.",
            is_read=True,
        )

        response = self.client.get("/api/notifications/", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 2)
        self.assertEqual(response.data["unread_count"], 1)

    def test_mark_single_notification_read(self):
        n = Notification.objects.create(
            workspace=self.workspace,
            recipient=self.user,
            actor=self.actor,
            notification_type="mention",
            title="Mentioned in channel",
            message="You were mentioned in #general.",
            is_read=False,
        )

        response = self.client.post(f"/api/notifications/{n.id}/read/", {}, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        n.refresh_from_db()
        self.assertTrue(n.is_read)

    def test_mark_all_notifications_read(self):
        for i in range(3):
            Notification.objects.create(
                workspace=self.workspace,
                recipient=self.user,
                actor=self.actor,
                notification_type="system",
                title=f"System Alert {i}",
                message="Maintenance scheduled.",
                is_read=False,
            )

        response = self.client.post("/api/notifications/mark-all-read/", {}, format="json", **self.headers)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        unread = Notification.objects.filter(workspace=self.workspace, recipient=self.user, is_read=False).count()
        self.assertEqual(unread, 0)
