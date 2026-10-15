from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from core.models import User, Workspace, WorkspaceMember
from communications.models import Conversation, ConversationMember, Message


class CommunicationsPollingAndPrivacyTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user1 = User.objects.create_user(email="alice@team.com", password="Pass1!", name="Alice")
        self.user2 = User.objects.create_user(email="bob@team.com", password="Pass2!", name="Bob")
        self.user3 = User.objects.create_user(email="eve@team.com", password="Pass3!", name="Eve")

        self.workspace = Workspace.objects.create(name="Productivity Co", owner=self.user1)
        self.m1 = WorkspaceMember.objects.create(workspace=self.workspace, user=self.user1, role="admin")
        self.m2 = WorkspaceMember.objects.create(workspace=self.workspace, user=self.user2, role="member")
        self.m3 = WorkspaceMember.objects.create(workspace=self.workspace, user=self.user3, role="member")

        # Public Channel
        self.channel = Conversation.objects.create(
            workspace=self.workspace, type="channel", name="general", created_by=self.user1
        )
        ConversationMember.objects.create(conversation=self.channel, user=self.user1)
        ConversationMember.objects.create(conversation=self.channel, user=self.user2)

        # Private DM between Alice and Bob
        self.dm = Conversation.objects.create(
            workspace=self.workspace, type="dm", is_private=True, created_by=self.user1
        )
        ConversationMember.objects.create(conversation=self.dm, user=self.user1)
        ConversationMember.objects.create(conversation=self.dm, user=self.user2)

    def test_incremental_polling_retrieval(self):
        self.client.force_authenticate(user=self.user1)
        headers = {"HTTP_X_WORKSPACE_ID": str(self.workspace.id)}

        # Seed 3 messages
        m1 = Message.objects.create(conversation=self.channel, sender=self.user1, content="Message 1")
        m2 = Message.objects.create(conversation=self.channel, sender=self.user2, content="Message 2")
        m3 = Message.objects.create(conversation=self.channel, sender=self.user1, content="Message 3")

        # Initial fetch
        url = f"/api/communications/conversations/{self.channel.id}/messages/"
        res = self.client.get(url, **headers)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data["results"]), 3)
        self.assertEqual(res.data["latest_id"], m3.id)

        # Subsequent incremental poll with after_id=m3.id -> should return 0 messages
        poll_res1 = self.client.get(f"{url}?after_id={m3.id}", **headers)
        self.assertEqual(poll_res1.status_code, status.HTTP_200_OK)
        self.assertEqual(len(poll_res1.data["results"]), 0)
        self.assertEqual(poll_res1.data["latest_id"], m3.id)

        # Post message 4
        m4 = Message.objects.create(conversation=self.channel, sender=self.user2, content="Message 4")

        # Incremental poll with after_id=m3.id -> should return ONLY message 4!
        poll_res2 = self.client.get(f"{url}?after_id={m3.id}", **headers)
        self.assertEqual(poll_res2.status_code, status.HTTP_200_OK)
        self.assertEqual(len(poll_res2.data["results"]), 1)
        self.assertEqual(poll_res2.data["results"][0]["id"], m4.id)
        self.assertEqual(poll_res2.data["results"][0]["content"], "Message 4")
        self.assertEqual(poll_res2.data["latest_id"], m4.id)

    def test_older_history_pagination(self):
        self.client.force_authenticate(user=self.user1)
        headers = {"HTTP_X_WORKSPACE_ID": str(self.workspace.id)}

        msgs = [
            Message.objects.create(conversation=self.channel, sender=self.user1, content=f"Msg {i}")
            for i in range(10)
        ]

        url = f"/api/communications/conversations/{self.channel.id}/messages/"
        # Query older messages before msg 5 with limit=3
        res = self.client.get(f"{url}?before_id={msgs[5].id}&limit=3", **headers)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data["results"]), 3)
        # Should be msg 2, 3, 4
        ids = [m["id"] for m in res.data["results"]]
        self.assertEqual(ids, [msgs[2].id, msgs[3].id, msgs[4].id])

    def test_private_dm_access_control(self):
        # Alice posts to DM
        Message.objects.create(conversation=self.dm, sender=self.user1, content="Top secret message")

        # Eve (not part of the DM) attempts to read or poll the DM
        self.client.force_authenticate(user=self.user3)
        headers = {"HTTP_X_WORKSPACE_ID": str(self.workspace.id)}

        url = f"/api/communications/conversations/{self.dm.id}/messages/"
        res = self.client.get(url, **headers)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class ChatMentionNotificationTests(TestCase):
    def setUp(self):
        from django.core import mail
        mail.outbox.clear()
        self.client = APIClient()
        self.alice = User.objects.create_user(email="alice@team.com", username="alice", password="Pass1!", name="Alice Walker")
        self.bob = User.objects.create_user(email="bob@team.com", username="bob", password="Pass2!", name="Bob Ross")
        self.eve = User.objects.create_user(email="eve@team.com", username="eve", password="Pass3!", name="Eve")

        self.workspace = Workspace.objects.create(name="Productivity Co", owner=self.alice)
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.alice, role="admin", status="active")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.bob, role="member", status="active")
        WorkspaceMember.objects.create(workspace=self.workspace, user=self.eve, role="member", status="active")

        self.channel = Conversation.objects.create(
            workspace=self.workspace, type="channel", name="general", created_by=self.alice
        )
        ConversationMember.objects.create(conversation=self.channel, user=self.alice)
        ConversationMember.objects.create(conversation=self.channel, user=self.bob)
        ConversationMember.objects.create(conversation=self.channel, user=self.eve)

    def test_mention_creates_notification_and_sends_email(self):
        from django.core import mail
        from notifications.models import Notification

        self.client.force_authenticate(user=self.alice)
        headers = {"HTTP_X_WORKSPACE_ID": str(self.workspace.id)}

        url = f"/api/communications/conversations/{self.channel.id}/messages/"
        response = self.client.post(
            url,
            {"content": "Hey @bob and @Bob Ross, please check the new deployment!"},
            format="json",
            **headers,
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Bob should receive exactly 1 mention notification (deduplicated)
        notifications = Notification.objects.filter(recipient=self.bob, notification_type="mention")
        self.assertEqual(notifications.count(), 1)
        notif = notifications.first()
        self.assertEqual(notif.actor, self.alice)
        self.assertIn("Alice Walker tagged you", notif.title)
        self.assertIn("Hey @bob and @Bob Ross", notif.message)

        # Alice should NOT receive a notification for tagging
        self.assertEqual(Notification.objects.filter(recipient=self.alice).count(), 0)

        # Email should have been sent to Bob
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ["bob@team.com"])
        self.assertIn("[Plate]", email.subject)
        self.assertIn("tagged you in a chat", email.subject)

    def test_self_mention_does_not_notify_sender(self):
        from django.core import mail
        from notifications.models import Notification

        self.client.force_authenticate(user=self.alice)
        headers = {"HTTP_X_WORKSPACE_ID": str(self.workspace.id)}

        url = f"/api/communications/conversations/{self.channel.id}/messages/"
        response = self.client.post(
            url,
            {"content": "Note to self: @alice remember to check this"},
            format="json",
            **headers,
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.assertEqual(Notification.objects.filter(recipient=self.alice).count(), 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_editing_message_notifies_newly_mentioned_user(self):
        from django.core import mail
        from notifications.models import Notification

        self.client.force_authenticate(user=self.alice)
        headers = {"HTTP_X_WORKSPACE_ID": str(self.workspace.id)}

        msg = Message.objects.create(
            conversation=self.channel,
            sender=self.alice,
            content="Hello everyone",
        )

        patch_url = f"/api/communications/messages/{msg.id}/"
        response = self.client.patch(
            patch_url,
            {"content": "Hello everyone, cc @eve!"},
            format="json",
            **headers,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        eve_notifs = Notification.objects.filter(recipient=self.eve, notification_type="mention")
        self.assertEqual(eve_notifs.count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["eve@team.com"])

    def test_chat_message_rejects_video_file(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_authenticate(user=self.alice)
        headers = {"HTTP_X_WORKSPACE_ID": str(self.workspace.id)}

        video_file = SimpleUploadedFile("screen_recording.mp4", b"fake mp4 video bytes", content_type="video/mp4")
        url = f"/api/communications/conversations/{self.channel.id}/messages/"
        res = self.client.post(
            url,
            {"file": video_file, "message_type": "file"},
            format="multipart",
            **headers,
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Video files are not allowed", res.data["error"])


