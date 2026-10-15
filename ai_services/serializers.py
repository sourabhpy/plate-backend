from rest_framework import serializers
from .models import DocumentAnalysis, VoiceExtraction
from core.serializers import UserSerializer


class DocumentAnalysisSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = DocumentAnalysis
        fields = [
            "id",
            "workspace",
            "file_name",
            "file_type",
            "file_url",
            "extracted_text",
            "summary",
            "key_findings",
            "issues",
            "suggested_tasks",
            "created_by",
            "created_at",
        ]

    def get_file_url(self, obj):
        if not obj.file:
            return None
        request = self.context.get("request")
        if request:
            try:
                return request.build_absolute_uri(obj.file.url)
            except Exception:
                pass
        try:
            return obj.file.url
        except Exception:
            return None


class VoiceExtractionSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)
    audio_url = serializers.SerializerMethodField()

    class Meta:
        model = VoiceExtraction
        fields = [
            "id",
            "workspace",
            "audio_url",
            "transcript",
            "decisions",
            "blockers",
            "extracted_tasks",
            "created_by",
            "created_at",
        ]

    def get_audio_url(self, obj):
        if not obj.audio_file:
            return None
        request = self.context.get("request")
        if request:
            try:
                return request.build_absolute_uri(obj.audio_file.url)
            except Exception:
                pass
        try:
            return obj.audio_file.url
        except Exception:
            return None
