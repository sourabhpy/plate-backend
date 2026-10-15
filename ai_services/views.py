import os
from rest_framework import status, views, permissions
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from core.permissions import IsWorkspaceMember, IsWorkspaceAdmin
from core.models import WorkspaceMember
from tasks.models import Task, TaskActivity
from communications.models import Message
from .models import DocumentAnalysis, VoiceExtraction, TeamMemoryChunk
from .voice_service import VoiceExtractionService
from .document_service import DocumentAnalysisService
from .rag_service import TeamMemoryRAGService
from .serializers import DocumentAnalysisSerializer, VoiceExtractionSerializer
from notifications.services import NotificationService
from core.media_validators import (
    validate_max_file_size,
    validate_not_video,
    get_audio_duration_seconds,
    MAX_AUDIO_ANALYSIS_DURATION_SECONDS,
)


class VoiceTranscribeAndExtractView(views.APIView):
    permission_classes = [IsWorkspaceMember]

    def post(self, request):
        if len(request.FILES) > 1:
            return Response(
                {"error": "Only one audio file can be processed at a time."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        audio_file = request.FILES.get("audio") or request.FILES.get("audio_file")
        transcript_text = request.data.get("transcript")
        is_direct_recording = str(request.data.get("is_direct_recording", "true")).lower() == "true"

        if not audio_file and not transcript_text:
            return Response(
                {"error": "Audio file or transcript text is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if audio_file:
            is_not_video, video_err = validate_not_video(audio_file)
            if not is_not_video:
                return Response({"error": video_err}, status=status.HTTP_400_BAD_REQUEST)

            is_valid_size, size_err = validate_max_file_size(audio_file, label="Audio file")
            if not is_valid_size:
                return Response({"error": size_err}, status=status.HTTP_400_BAD_REQUEST)

            duration = get_audio_duration_seconds(audio_file)
            if duration is not None and duration > (MAX_AUDIO_ANALYSIS_DURATION_SECONDS + 0.5):
                return Response(
                    {
                        "error": f"Audio exceeds the 1-minute limit ({int(round(duration))}s). Please provide an audio recording under 60 seconds."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        extraction_record = VoiceExtraction.objects.create(
            workspace=request.workspace,
            audio_file=audio_file,
            created_by=request.user,
        )

        if not transcript_text and audio_file:
            transcript_text = VoiceExtractionService.transcribe_audio_file(
                extraction_record.audio_file.path,
                mime_type=audio_file.content_type or "audio/webm",
            )

        extraction_record.transcript = transcript_text

        # Structured Task Extraction with Attribution & Evidence
        extracted_data = VoiceExtractionService.extract_structured_tasks(
            transcript=transcript_text,
            workspace=request.workspace,
            current_user=request.user,
            is_direct_recording=is_direct_recording,
        )

        extraction_record.decisions = extracted_data.get("decisions", [])
        extraction_record.blockers = extracted_data.get("blockers", [])
        extraction_record.extracted_tasks = extracted_data.get("tasks", [])
        extraction_record.save()

        # Automatically index voice transcript into team memory
        TeamMemoryRAGService.index_chunk(
            workspace=request.workspace,
            source_type="voice_note",
            source_id=str(extraction_record.id),
            title=f"Voice Note ({extraction_record.created_at.strftime('%b %d, %H:%M')})",
            content=transcript_text,
            metadata={"author": request.user.name, "created_at": str(extraction_record.created_at)},
        )

        return Response({
            "extraction_id": extraction_record.id,
            "transcript": transcript_text,
            "decisions": extraction_record.decisions,
            "blockers": extraction_record.blockers,
            "tasks": extraction_record.extracted_tasks,
        }, status=status.HTTP_200_OK)


class ExtractTaskFromMessageView(views.APIView):
    permission_classes = [IsWorkspaceMember]

    def post(self, request):
        message_id = request.data.get("message_id")
        if not message_id:
            return Response({"error": "message_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        message = get_object_or_404(Message, id=message_id, conversation__workspace=request.workspace)

        content = message.content
        if message.message_type == "audio" and message.audio_file and not content:
            content = VoiceExtractionService.transcribe_audio_file(message.audio_file.path)
        elif message.message_type == "file" and message.file and not content:
            file_name = (message.file_name or message.file.name).lower()
            if any(file_name.endswith(ext) for ext in [".webm", ".mp3", ".wav", ".m4a", ".ogg", ".aac", ".flac"]):
                content = VoiceExtractionService.transcribe_audio_file(message.file.path)

        extracted_data = VoiceExtractionService.extract_structured_tasks(
            transcript=content,
            workspace=request.workspace,
            current_user=message.sender,
            is_direct_recording=False,
        )

        return Response({
            "message_id": message.id,
            "content": content,
            "decisions": extracted_data.get("decisions", []),
            "blockers": extracted_data.get("blockers", []),
            "tasks": extracted_data.get("tasks", []),
        })


class CommitExtractedTasksView(views.APIView):
    """
    Commits reviewed tasks to the workspace task board with full validation,
    activity logging, source tracking, and duplicate prevention.
    """
    permission_classes = [IsWorkspaceMember]

    def post(self, request):
        tasks_data = request.data.get("tasks", [])
        source_type = request.data.get("source_type", "voice_extraction")
        source_id = str(request.data.get("source_id", ""))

        if not tasks_data:
            return Response({"error": "No tasks provided to commit"}, status=status.HTTP_400_BAD_REQUEST)

        created_tasks = []
        for item in tasks_data:
            title = item.get("title", "").strip()
            if not title:
                continue

            # Prevent duplicate tasks from same source with identical title
            existing = Task.objects.filter(
                workspace=request.workspace,
                title=title,
                source_type=source_type,
                source_id=source_id,
            ).first()
            if existing:
                created_tasks.append(existing)
                continue

            assignee = None
            assignee_id = item.get("assignee_id")
            if assignee_id:
                assignee = WorkspaceMember.objects.filter(id=assignee_id, workspace=request.workspace).first()

            task = Task.objects.create(
                workspace=request.workspace,
                title=title,
                description=item.get("description", ""),
                assignee=assignee,
                creator=request.user,
                status=item.get("status", "inbox"),
                priority=item.get("priority", "medium"),
                deadline=item.get("deadline") or None,
                source_type=source_type,
                source_id=source_id,
                evidence_quote=item.get("evidence_quote", ""),
            )

            TaskActivity.objects.create(
                task=task,
                actor=request.user,
                field_name="created",
                old_value="",
                new_value=task.title,
                description=f"Created via AI task extraction from {source_type}",
            )

            # Auto-index task into team memory
            TeamMemoryRAGService.index_chunk(
                workspace=request.workspace,
                source_type="task",
                source_id=str(task.id),
                title=f"Task: {task.title}",
                content=f"Title: {task.title}\nDescription: {task.description}\nAssignee: {assignee.user.name if assignee else 'Unassigned'}\nPriority: {task.priority}",
            )

            if assignee and assignee.user != request.user:
                NotificationService.notify_task_assignment(
                    task=task,
                    actor=request.user,
                    assignee=assignee.user,
                    action_type="assigned",
                )

            created_tasks.append(task)

        return Response({
            "message": f"Successfully created {len(created_tasks)} tasks",
            "task_ids": [t.id for t in created_tasks],
        }, status=status.HTTP_201_CREATED)


class DocumentAnalyzeView(views.APIView):
    permission_classes = [IsWorkspaceMember]

    def post(self, request):
        if len(request.FILES) > 1:
            return Response(
                {"error": "Only one document can be analyzed at a time."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        file_obj = request.FILES.get("file")
        if not file_obj:
            return Response({"error": "File is required"}, status=status.HTTP_400_BAD_REQUEST)

        is_not_video, video_err = validate_not_video(file_obj)
        if not is_not_video:
            return Response({"error": video_err}, status=status.HTTP_400_BAD_REQUEST)

        is_valid_size, size_err = validate_max_file_size(file_obj, label="Document file")
        if not is_valid_size:
            return Response({"error": size_err}, status=status.HTTP_400_BAD_REQUEST)

        doc = DocumentAnalysis.objects.create(
            workspace=request.workspace,
            file=file_obj,
            file_name=file_obj.name,
            file_type=file_obj.content_type or "",
            created_by=request.user,
        )

        extracted_text = DocumentAnalysisService.extract_text(
            doc.file.path,
            mime_type=file_obj.content_type or "",
        )
        doc.extracted_text = extracted_text

        analysis_result = DocumentAnalysisService.analyze_document(
            text=extracted_text,
            file_name=file_obj.name,
        )

        doc.summary = analysis_result.get("summary", "")
        doc.key_findings = analysis_result.get("key_findings", [])
        doc.issues = analysis_result.get("issues", [])
        doc.suggested_tasks = analysis_result.get("suggested_tasks", [])
        doc.save()

        # Index document analysis into Team Memory (executive summary and full content sections)
        TeamMemoryRAGService.index_document(request.workspace, doc, user=request.user)

        return Response({
            "id": doc.id,
            "file_name": doc.file_name,
            "summary": doc.summary,
            "key_findings": doc.key_findings,
            "issues": doc.issues,
            "suggested_tasks": doc.suggested_tasks,
        }, status=status.HTTP_200_OK)


class AskTeamMemoryView(views.APIView):
    """
    RAG & Knowledge Retrieval endpoint.
    Answers natural language inquiries about past discussions, decisions, current member status, etc.
    """
    permission_classes = [IsWorkspaceMember]

    def post(self, request):
        question = request.data.get("question", "").strip()
        if not question:
            return Response({"error": "Question is required"}, status=status.HTTP_400_BAD_REQUEST)

        rag_response = TeamMemoryRAGService.answer_question(
            workspace=request.workspace,
            query_text=question,
            user=request.user,
        )

        return Response(rag_response, status=status.HTTP_200_OK)


class IndexWorkspaceContentBatchView(views.APIView):
    """
    Batch indexes existing chat messages, decisions, and tasks into Team Memory.
    """
    permission_classes = [IsWorkspaceMember]

    def post(self, request):
        indexed_count = 0

        # Index public channel messages
        messages = Message.objects.filter(
            conversation__workspace=request.workspace,
            conversation__type="channel",
            conversation__is_private=False,
            message_type="text"
        ).select_related("sender", "conversation")[:50]

        for msg in messages:
            if len(msg.content.strip()) > 15:
                TeamMemoryRAGService.index_chunk(
                    workspace=request.workspace,
                    source_type="message",
                    source_id=str(msg.id),
                    title=f"Message in #{msg.conversation.name} by {msg.sender.name}",
                    content=msg.content,
                    metadata={"conversation_id": str(msg.conversation.id), "sender": msg.sender.name},
                )
                indexed_count += 1

        # Index active tasks
        tasks = Task.objects.filter(workspace=request.workspace)[:50]
        for t in tasks:
            TeamMemoryRAGService.index_chunk(
                workspace=request.workspace,
                source_type="task",
                source_id=str(t.id),
                title=f"Task: {t.title}",
                content=f"Title: {t.title}\nDescription: {t.description}\nStatus: {t.status}\nPriority: {t.priority}",
            )
            indexed_count += 1

        return Response({
            "message": f"Successfully indexed {indexed_count} items into team memory",
            "indexed_count": indexed_count,
        })


class DocumentAnalysisHistoryView(views.APIView):
    """
    Returns history of all document analyses performed in this workspace.
    Restricted strictly to Workspace Admins.
    """
    permission_classes = [IsWorkspaceAdmin]

    def get(self, request):
        analyses = DocumentAnalysis.objects.filter(
            workspace=request.workspace
        ).select_related("created_by").order_by("-created_at")
        serializer = DocumentAnalysisSerializer(analyses, many=True, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class VoiceExtractionHistoryView(views.APIView):
    """
    Returns history of all voice and audio task extractions performed in this workspace.
    Restricted strictly to Workspace Admins.
    """
    permission_classes = [IsWorkspaceAdmin]

    def get(self, request):
        extractions = VoiceExtraction.objects.filter(
            workspace=request.workspace
        ).select_related("created_by").order_by("-created_at")
        serializer = VoiceExtractionSerializer(extractions, many=True, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

