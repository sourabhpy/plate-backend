from django.contrib import admin
from .models import DocumentAnalysis, TeamMemoryChunk


@admin.register(DocumentAnalysis)
class DocumentAnalysisAdmin(admin.ModelAdmin):
    list_display = ("file_name", "workspace", "file_type", "created_at")
    search_fields = ("file_name", "summary")


@admin.register(TeamMemoryChunk)
class TeamMemoryChunkAdmin(admin.ModelAdmin):
    list_display = ("title", "workspace", "source_type", "source_id", "created_at")
    list_filter = ("source_type", "workspace")
    search_fields = ("title", "content")
