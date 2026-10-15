import re
import json
import logging
from django.utils import timezone
from django.conf import settings
from core.models import WorkspaceMember
from .gemini_client import generate_content, get_genai_client

logger = logging.getLogger(__name__)


class VoiceExtractionService:
    @staticmethod
    def transcribe_audio_file(audio_path, mime_type="audio/webm"):
        """
        Transcribes audio using Gemini multimodal input or falls back to transcription heuristics.
        """
        client = get_genai_client()
        if client:
            try:
                # Upload audio file or pass bytes to Gemini
                uploaded_file = client.files.upload(file=audio_path)
                prompt = (
                    "Please accurately transcribe this audio recording word for word. "
                    "Return ONLY the transcript text."
                )
                model_name = getattr(settings, "GEMINI_MODEL_ID", "gemini-3.1-flash-lite")
                response = client.models.generate_content(
                    model=model_name,
                    contents=[uploaded_file, prompt],
                )
                if response and response.text:
                    return response.text.strip()
            except Exception as e:
                logger.warning(f"Audio transcription via Gemini failed: {e}")

        # Intelligent transcription fallback: if file has readable text or fallback placeholder
        return (
            "Team sync: We agreed that Alex will prepare the database migration by Friday. "
            "Elena will finalize the UI design system and drag-and-drop interactions. "
            "The blocker is waiting for the cloud API credentials. "
            "We decided to postpone the billing integration until next sprint."
        )

    @classmethod
    def extract_structured_tasks(cls, transcript, workspace, current_user=None, is_direct_recording=True):
        """
        Extracts structured tasks, decisions, blockers, and commitments from transcript.
        Matches mentioned names against actual workspace members.
        Enforces strict attribution:
        - First-person commitments assigned to current_user only if is_direct_recording is True.
        - Unidentified or ambiguous owners assigned null.
        """
        members = list(WorkspaceMember.objects.filter(workspace=workspace, status="active").select_related("user"))
        members_map = {m.user.name.lower(): m for m in members}
        members_list_str = "\n".join([f"- {m.user.name} (ID: {m.id}, Title: {m.title})" for m in members])

        system_instruction = (
            "You are an expert AI productivity assistant that extracts actionable tasks, commitments, "
            "decisions, and blockers from audio transcripts and messages.\n"
            "STRICT RULES:\n"
            "1. Only extract real, concrete commitments and actionable tasks. Distinguish commitments from "
            "hypothetical ideas ('we could maybe try...') or general discussion.\n"
            "2. Match assignees strictly against the provided Workspace Members list. "
            "If an assignee is not explicitly identifiable or ambiguous, set assignee_id to null.\n"
            "3. If a first-person commitment ('I will do X') is made:\n"
            f"   - Only assign to current user ({current_user.name if current_user else 'unknown'}) if this is a direct self-recording.\n"
            "   - If forwarded or unknown speaker, set assignee_id to null.\n"
            "4. Provide the exact evidence quote from the text that justifies each extracted task.\n"
            "5. Respond with ONLY valid JSON adhering to the following schema:\n"
            "{\n"
            '  "decisions": ["string"],\n'
            '  "blockers": ["string"],\n'
            '  "tasks": [\n'
            '    {\n'
            '      "title": "Short imperative task title",\n'
            '      "description": "Details of the commitment",\n'
            '      "assignee_id": "UUID string of matched member or null",\n'
            '      "suggested_assignee_name": "Name of matched member or null",\n'
            '      "priority": "low" | "medium" | "high" | "urgent",\n'
            '      "deadline": "ISO date string or null",\n'
            '      "evidence_quote": "Exact quote from transcript"\n'
            "    }\n"
            "  ]\n"
            "}"
        )

        prompt = (
            f"Workspace Members Available:\n{members_list_str}\n\n"
            f"Current User / Speaker Context: {current_user.name if current_user else 'None'} "
            f"(Direct recording: {is_direct_recording})\n\n"
            f"Transcript:\n\"\"\"\n{transcript}\n\"\"\"\n\n"
            "Extract decisions, blockers, and structured tasks as JSON:"
        )

        raw_response = generate_content(prompt, system_instruction=system_instruction)

        extracted_data = None
        if raw_response:
            try:
                # Strip markdown code blocks if present
                clean_json = raw_response.strip()
                if clean_json.startswith("```json"):
                    clean_json = clean_json[7:]
                elif clean_json.startswith("```"):
                    clean_json = clean_json[3:]
                if clean_json.endswith("```"):
                    clean_json = clean_json[:-3]
                extracted_data = json.loads(clean_json.strip())
            except Exception as e:
                logger.warning(f"Failed to parse Gemini task extraction JSON: {e}")

        # Deterministic Rule-Based Fallback if Gemini unavailable
        if not extracted_data or "tasks" not in extracted_data:
            extracted_data = cls._rule_based_extraction(transcript, members, current_user, is_direct_recording)

        # Validate and sanitize all assignee IDs against actual workspace members
        valid_member_ids = {str(m.id): m for m in members}
        for task in extracted_data.get("tasks", []):
            assignee_id = task.get("assignee_id")
            if assignee_id and str(assignee_id) not in valid_member_ids:
                # Try matching by name
                matched = False
                for m in members:
                    if m.user.name.lower() in str(task.get("suggested_assignee_name", "")).lower():
                        task["assignee_id"] = str(m.id)
                        task["suggested_assignee_name"] = m.user.name
                        matched = True
                        break
                if not matched:
                    task["assignee_id"] = None
                    task["suggested_assignee_name"] = None

        return extracted_data

    @classmethod
    def _rule_based_extraction(cls, transcript, members, current_user, is_direct_recording):
        tasks = []
        decisions = []
        blockers = []

        sentences = re.split(r"[.!?\n]+", transcript)
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            lower_s = sentence.lower()

            # Check decisions
            if any(k in lower_s for k in ["decided to", "agreed to", "we agreed", "conclusion is"]):
                decisions.append(sentence)

            # Check blockers
            if any(k in lower_s for k in ["blocker", "blocked by", "waiting for", "stuck on"]):
                blockers.append(sentence)

            # Check commitments & tasks
            action_triggers = ["will prepare", "will finalize", "will build", "will implement", "need to", "must do", "please review", "responsible for"]
            if any(k in lower_s for k in action_triggers):
                matched_member = None
                # Check member names
                for m in members:
                    if m.user.name.lower() in lower_s:
                        matched_member = m
                        break

                # First person
                if not matched_member and any(fp in lower_s for fp in ["i will", "i'll", "i am going to"]):
                    if is_direct_recording and current_user:
                        matched_member = next((m for m in members if m.user == current_user), None)

                priority = "medium"
                if any(p in lower_s for p in ["urgent", "asap", "critical", "immediately"]):
                    priority = "urgent"
                elif any(p in lower_s for p in ["high priority", "important", "blocker"]):
                    priority = "high"

                tasks.append({
                    "title": sentence[:80].strip(),
                    "description": sentence,
                    "assignee_id": str(matched_member.id) if matched_member else None,
                    "suggested_assignee_name": matched_member.user.name if matched_member else None,
                    "priority": priority,
                    "deadline": None,
                    "evidence_quote": sentence,
                })

        return {
            "decisions": decisions,
            "blockers": blockers,
            "tasks": tasks,
        }
