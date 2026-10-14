from django.urls import path
from .views import (
    VoiceTranscribeAndExtractView,
    ExtractTaskFromMessageView,
    CommitExtractedTasksView,
    DocumentAnalyzeView,
    AskTeamMemoryView,
    IndexWorkspaceContentBatchView,
)

urlpatterns = [
    path("voice/transcribe-extract/", VoiceTranscribeAndExtractView.as_view(), name="voice-transcribe-extract"),
    path("tasks/extract-from-message/", ExtractTaskFromMessageView.as_view(), name="extract-from-message"),
    path("tasks/commit-extracted/", CommitExtractedTasksView.as_view(), name="commit-extracted-tasks"),
    path("documents/analyze/", DocumentAnalyzeView.as_view(), name="document-analyze"),
    path("memory/ask/", AskTeamMemoryView.as_view(), name="memory-ask"),
    path("memory/index-batch/", IndexWorkspaceContentBatchView.as_view(), name="memory-index-batch"),
]
