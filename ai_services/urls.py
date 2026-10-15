from django.urls import path
from .views import (
    VoiceTranscribeAndExtractView,
    ExtractTaskFromMessageView,
    CommitExtractedTasksView,
    DocumentAnalyzeView,
    AskTeamMemoryView,
    IndexWorkspaceContentBatchView,
    DocumentAnalysisHistoryView,
    VoiceExtractionHistoryView,
)

urlpatterns = [
    path("voice/transcribe-extract/", VoiceTranscribeAndExtractView.as_view(), name="voice-transcribe-extract"),
    path("voice/history/", VoiceExtractionHistoryView.as_view(), name="voice-history"),
    path("tasks/extract-from-message/", ExtractTaskFromMessageView.as_view(), name="extract-from-message"),
    path("tasks/commit-extracted/", CommitExtractedTasksView.as_view(), name="commit-extracted-tasks"),
    path("documents/analyze/", DocumentAnalyzeView.as_view(), name="document-analyze"),
    path("documents/history/", DocumentAnalysisHistoryView.as_view(), name="document-history"),
    path("memory/ask/", AskTeamMemoryView.as_view(), name="memory-ask"),
    path("ask-memory/", AskTeamMemoryView.as_view(), name="ask-memory"),
    path("memory/index-batch/", IndexWorkspaceContentBatchView.as_view(), name="memory-index-batch"),
    path("batch-index/", IndexWorkspaceContentBatchView.as_view(), name="batch-index"),
]
