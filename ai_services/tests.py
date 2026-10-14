from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from core.models import User, Workspace, WorkspaceMember
from tasks.models import Task
from ai_services.voice_service import VoiceExtractionService
from ai_services.rag_service import TeamMemoryRAGService
from ai_services.document_service import DocumentAnalysisService


class AIServicesTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(email="carol@tech.com", password="Pass1!", name="Carol")
        self.dev = User.objects.create_user(email="dave@tech.com", password="Pass2!", name="Dave")
        self.workspace = Workspace.objects.create(name="Tech Labs", owner=self.user)
        self.m1 = WorkspaceMember.objects.create(workspace=self.workspace, user=self.user, role="admin")
        self.m2 = WorkspaceMember.objects.create(workspace=self.workspace, user=self.dev, role="member")
        self.client.force_authenticate(user=self.user)

    def test_voice_task_extraction_attribution_and_member_matching(self):
        transcript = (
            "During our sprint review, Dave will prepare the database migration by Thursday. "
            "We decided to postpone the analytics dashboard. "
            "The blocker is waiting for staging environment access."
        )

        data = VoiceExtractionService.extract_structured_tasks(
            transcript=transcript,
            workspace=self.workspace,
            current_user=self.user,
            is_direct_recording=True,
        )

        self.assertIn("decisions", data)
        self.assertIn("blockers", data)
        self.assertIn("tasks", data)
        self.assertTrue(len(data["tasks"]) >= 1)

        # Verify Dave was matched as assignee
        task = data["tasks"][0]
        self.assertEqual(task["assignee_id"], str(self.m2.id))
        self.assertIn("evidence_quote", task)

    def test_commit_extracted_tasks_endpoint(self):
        tasks_payload = [
            {
                "title": "Prepare database migration",
                "description": "Database migration by Thursday",
                "assignee_id": str(self.m2.id),
                "priority": "high",
                "evidence_quote": "Dave will prepare the database migration",
            }
        ]

        response = self.client.post("/api/ai/tasks/commit-extracted/", {
            "tasks": tasks_payload,
            "source_type": "voice_transcript",
            "source_id": "test-voice-123"
        }, format="json", HTTP_X_WORKSPACE_ID=str(self.workspace.id))

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data["task_ids"]), 1)

        # Verify task is created in DB
        task = Task.objects.get(id=response.data["task_ids"][0])
        self.assertEqual(task.title, "Prepare database migration")
        self.assertEqual(task.assignee, self.m2)

    def test_team_memory_rag_indexing_and_answering(self):
        # Index decision into team memory
        TeamMemoryRAGService.index_chunk(
            workspace=self.workspace,
            source_type="decision",
            source_id="planning-dec-1",
            title="Postpone Analytics Dashboard",
            content="We decided to postpone the analytics dashboard due to lack of cloud API credentials.",
        )

        # Ask question
        res = TeamMemoryRAGService.answer_question(
            workspace=self.workspace,
            query_text="Why was the analytics dashboard postponed?",
            user=self.user,
        )

        self.assertIn("answer", res)
        self.assertIn("citations", res)
        self.assertTrue(len(res["citations"]) >= 1)
        self.assertEqual(res["citations"][0]["title"], "Postpone Analytics Dashboard")
