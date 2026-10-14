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
