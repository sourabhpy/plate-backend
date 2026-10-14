import numpy as np
import logging
from django.db.models import Q
from tasks.models import Task
from core.models import WorkspaceMember
from communications.models import Conversation, Message
from .models import TeamMemoryChunk
from .gemini_client import generate_embedding, generate_content

logger = logging.getLogger(__name__)


class TeamMemoryRAGService:
    @classmethod
    def index_chunk(cls, workspace, source_type, source_id, title, content, metadata=None):
        """
        Embeds and stores a text chunk into the workspace team memory.
        """
        if not content.strip():
            return None

        embedding_vector = generate_embedding(f"{title}\n{content}")
        
        # Check if already indexed to prevent duplicates
        chunk, created = TeamMemoryChunk.objects.update_or_create(
            workspace=workspace,
            source_type=source_type,
            source_id=str(source_id),
            defaults={
                "title": title,
                "content": content,
                "embedding": embedding_vector,
                "metadata": metadata or {},
            }
        )
        return chunk

    @classmethod
    def search_similar_chunks(cls, workspace, query_text, user=None, top_k=5):
        """
        Calculates cosine similarity between query and stored team memory chunks.
        Strictly enforces workspace isolation and message visibility rules.
        """
        query_vec = np.array(generate_embedding(query_text), dtype=np.float32)
        query_norm = np.linalg.norm(query_vec)
        if query_norm == 0:
            return []

        chunks = list(TeamMemoryChunk.objects.filter(workspace=workspace))
        if not chunks:
            return []

        # Find which private conversations this user is allowed to access
        allowed_conv_ids = set()
        if user and user.is_authenticated:
            allowed_conv_ids = set(
                Conversation.objects.filter(
                    workspace=workspace
                ).filter(
                    Q(type="channel", is_private=False) | Q(members__user=user)
                ).values_list("id", flat=True)
            )

        scored_chunks = []
        for chunk in chunks:
            # Enforce message privacy
            if chunk.source_type == "message":
                conv_id = chunk.metadata.get("conversation_id")
                if conv_id and conv_id not in [str(c) for c in allowed_conv_ids]:
                    continue

            chunk_vec = np.array(chunk.embedding, dtype=np.float32)
            chunk_norm = np.linalg.norm(chunk_vec)
            if chunk_norm == 0:
                continue

            similarity = float(np.dot(query_vec, chunk_vec) / (query_norm * chunk_norm))
            scored_chunks.append((similarity, chunk))

        # Sort descending by cosine similarity
        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        return scored_chunks[:top_k]

    @classmethod
    def answer_question(cls, workspace, query_text, user=None):
        """
        Hybrid answering:
        1. Queries authoritative database for live facts (who is working on what, active tasks, roles).
        2. Retrieves historical vector context via RAG for discussions, decisions, and rationale.
        3. Formulates a grounded response citing supporting sources.
        """
        # 1. Authoritative structured state
        active_members = WorkspaceMember.objects.filter(workspace=workspace, status="active").select_related("user")
        tasks = Task.objects.filter(workspace=workspace).select_related("assignee__user", "project")

        structured_facts = []
        structured_facts.append(f"Workspace: {workspace.name}")
        structured_facts.append("Current Workspace Members:")
        for m in active_members:
            assigned_tasks = [t.title for t in tasks if t.assignee == m]
            task_str = f"Currently working on: {', '.join(assigned_tasks)}" if assigned_tasks else "No active tasks assigned."
            structured_facts.append(f"- {m.user.name} ({m.title}, Role: {m.role}). {task_str}")

        structured_facts.append("\nCurrent Tasks & Statuses:")
        for t in tasks[:30]:
            assignee_name = t.assignee.user.name if t.assignee else "Unassigned"
            deadline_str = f", Due: {t.deadline.strftime('%Y-%m-%d')}" if t.deadline else ""
            structured_facts.append(f"- [{t.status.upper()}] '{t.title}' (Assignee: {assignee_name}, Priority: {t.priority}{deadline_str})")

        structured_context_str = "\n".join(structured_facts)

        # 2. Semantic Search over Memory Chunks
        similar_chunks = cls.search_similar_chunks(workspace, query_text, user=user, top_k=6)
        
        memory_context = []
        citations = []
        for score, chunk in similar_chunks:
            memory_context.append(f"[{chunk.source_type.upper()}: {chunk.title}] (Score: {score:.2f})\n{chunk.content}")
            citations.append({
                "source_type": chunk.source_type,
                "source_id": chunk.source_id,
                "title": chunk.title,
                "score": round(score, 3),
            })

        memory_context_str = "\n\n".join(memory_context) if memory_context else "No historical records found matching this inquiry."

        system_instruction = (
            "You are Plate's AI Team Memory and RAG Assistant. Answer the user's question accurately.\n"
            "STRICT RULES:\n"
            "1. For questions about CURRENT state (who is working on what, member roles, deadlines, task statuses), "
            "rely strictly on the AUTHORITATIVE DATABASE RECORDS.\n"
            "2. For questions about past discussions, rationale, why decisions were made, or lessons learned, "
            "synthesize information from the HISTORICAL TEAM MEMORY.\n"
            "3. If sufficient evidence cannot be found in the provided context, state clearly and honestly: "
            "'I do not have enough historical information or recorded evidence to answer that question.' "
            "Never invent or hallucinate answers.\n"
            "4. Cite your sources clearly at the end of your response."
        )

        prompt = (
            f"User Question: {query_text}\n\n"
            f"AUTHORITATIVE DATABASE RECORDS (Current Live State):\n{structured_context_str}\n\n"
            f"HISTORICAL TEAM MEMORY (RAG Retrieval Context):\n{memory_context_str}\n\n"
            "Answer the question thoroughly, accurately, and honestly with clear citations:"
        )

        ai_response = generate_content(prompt, system_instruction=system_instruction)

        if not ai_response:
            # Deterministic fallback answering
            query_lower = query_text.lower()
            if "working on" in query_lower or "current" in query_lower:
                ai_response = f"Based on live authoritative records:\n" + "\n".join(structured_facts[1:5])
            elif similar_chunks:
                top_c = similar_chunks[0][1]
                ai_response = f"Based on team records: In '{top_c.title}', it was noted that: {top_c.content[:200]}..."
            else:
                ai_response = "I do not have enough recorded evidence or historical context in the team memory to answer this question."

        return {
            "answer": ai_response,
            "citations": citations,
        }
