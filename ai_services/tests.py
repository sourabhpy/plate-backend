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

    def test_admin_can_access_ai_history(self):
        from ai_services.models import DocumentAnalysis, VoiceExtraction

        # Seed document analysis
        doc = DocumentAnalysis.objects.create(
            workspace=self.workspace,
            file_name="Architecture_Spec.pdf",
            file_type="application/pdf",
            summary="System architecture overview",
            key_findings=["PostgreSQL selected", "pgvector used for RAG"],
            issues=["Connection limits require PgBouncer"],
            suggested_tasks=[{"title": "Deploy PgBouncer", "priority": "high"}],
            created_by=self.user,
        )

        # Seed voice extraction
        voice = VoiceExtraction.objects.create(
            workspace=self.workspace,
            transcript="We agreed to implement back stack navigation.",
            decisions=["Use history API pushState"],
            blockers=[],
            extracted_tasks=[{"title": "Implement back stack", "priority": "urgent"}],
            created_by=self.user,
        )

        # Admin fetches document history
        self.client.force_authenticate(user=self.user)
        headers = {"HTTP_X_WORKSPACE_ID": str(self.workspace.id)}
        res_doc = self.client.get("/api/ai/documents/history/", **headers)
        self.assertEqual(res_doc.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_doc.data), 1)
        self.assertEqual(res_doc.data[0]["file_name"], "Architecture_Spec.pdf")
        self.assertEqual(res_doc.data[0]["summary"], "System architecture overview")

        # Admin fetches voice history
        res_voice = self.client.get("/api/ai/voice/history/", **headers)
        self.assertEqual(res_voice.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_voice.data), 1)
        self.assertEqual(res_voice.data[0]["transcript"], "We agreed to implement back stack navigation.")

    def test_non_admin_forbidden_from_ai_history(self):
        # Non-admin member (dave) tries to access history
        self.client.force_authenticate(user=self.dev)
        headers = {"HTTP_X_WORKSPACE_ID": str(self.workspace.id)}

        res_doc = self.client.get("/api/ai/documents/history/", **headers)
        self.assertEqual(res_doc.status_code, status.HTTP_403_FORBIDDEN)

        res_voice = self.client.get("/api/ai/voice/history/", **headers)
        self.assertEqual(res_voice.status_code, status.HTTP_403_FORBIDDEN)

    def test_voice_extraction_rejects_audio_greater_than_5mb(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_authenticate(user=self.user)
        oversized = SimpleUploadedFile("long_audio.webm", b"0" * (6 * 1024 * 1024), content_type="audio/webm")
        res = self.client.post(
            "/api/ai/voice/transcribe-extract/",
            {"audio": oversized},
            format="multipart",
            HTTP_X_WORKSPACE_ID=str(self.workspace.id),
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("5MB", res.data["error"])

    def test_voice_extraction_rejects_multiple_audio_files(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_authenticate(user=self.user)
        audio1 = SimpleUploadedFile("audio1.webm", b"fake audio 1", content_type="audio/webm")
        audio2 = SimpleUploadedFile("audio2.webm", b"fake audio 2", content_type="audio/webm")
        res = self.client.post(
            "/api/ai/voice/transcribe-extract/",
            {"audio": audio1, "extra_file": audio2},
            format="multipart",
            HTTP_X_WORKSPACE_ID=str(self.workspace.id),
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Only one audio file", res.data["error"])

    def test_voice_extraction_rejects_audio_longer_than_1_minute(self):
        from unittest.mock import patch
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_authenticate(user=self.user)
        audio = SimpleUploadedFile("speech.webm", b"valid audio data", content_type="audio/webm")

        with patch("ai_services.views.get_audio_duration_seconds", return_value=75.0):
            res = self.client.post(
                "/api/ai/voice/transcribe-extract/",
                {"audio": audio},
                format="multipart",
                HTTP_X_WORKSPACE_ID=str(self.workspace.id),
            )
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("1-minute limit", res.data["error"])

    def test_document_analysis_rejects_file_greater_than_5mb(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_authenticate(user=self.user)
        oversized = SimpleUploadedFile("huge_doc.pdf", b"0" * (6 * 1024 * 1024), content_type="application/pdf")
        res = self.client.post(
            "/api/ai/documents/analyze/",
            {"file": oversized},
            format="multipart",
            HTTP_X_WORKSPACE_ID=str(self.workspace.id),
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("5MB", res.data["error"])

    def test_document_analysis_rejects_multiple_files(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_authenticate(user=self.user)
        f1 = SimpleUploadedFile("doc1.pdf", b"pdf1", content_type="application/pdf")
        f2 = SimpleUploadedFile("doc2.pdf", b"pdf2", content_type="application/pdf")
        res = self.client.post(
            "/api/ai/documents/analyze/",
            {"file": f1, "extra": f2},
            format="multipart",
            HTTP_X_WORKSPACE_ID=str(self.workspace.id),
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Only one document", res.data["error"])

    def test_voice_extraction_rejects_video_file(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_authenticate(user=self.user)
        video_file = SimpleUploadedFile("demo.mp4", b"fake video bytes", content_type="video/mp4")
        res = self.client.post(
            "/api/ai/voice/transcribe-extract/",
            {"audio": video_file},
            format="multipart",
            HTTP_X_WORKSPACE_ID=str(self.workspace.id),
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Video files are not allowed", res.data["error"])

    def test_document_analysis_rejects_video_file(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_authenticate(user=self.user)
        video_file = SimpleUploadedFile("recording.mov", b"fake video bytes", content_type="video/quicktime")
        res = self.client.post(
            "/api/ai/documents/analyze/",
            {"file": video_file},
            format="multipart",
            HTTP_X_WORKSPACE_ID=str(self.workspace.id),
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Video files are not allowed", res.data["error"])


