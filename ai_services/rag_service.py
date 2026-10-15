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
    def index_document(cls, workspace, doc, user=None):
        """
        Indexes a DocumentAnalysis record into team memory with both high-level executive summary,
        findings, issues, and content sections so detailed technical rationale and decisions are searchable.
        """
        summary_text = (
            f"Document: {doc.file_name}\n\n"
            f"Summary: {doc.summary}\n\n"
            f"Key Findings: {'; '.join(doc.key_findings) if doc.key_findings else 'N/A'}\n\n"
            f"Flagged Risks: {'; '.join(doc.issues) if doc.issues else 'N/A'}"
        )
        # 1. Main synthesis chunk
        cls.index_chunk(
            workspace=workspace,
            source_type="document",
            source_id=str(doc.id),
            title=f"Document: {doc.file_name} (Executive Summary)",
            content=summary_text,
            metadata={"file_name": doc.file_name, "uploader": user.name if user else (doc.created_by.name if doc.created_by else "")},
        )

        # 2. Detailed content chunk(s) if extracted text is available
        if doc.extracted_text and len(doc.extracted_text.strip()) > 50:
            text = doc.extracted_text.strip()
            if len(text) <= 5000:
                cls.index_chunk(
                    workspace=workspace,
                    source_type="document",
                    source_id=f"{doc.id}-content",
                    title=f"Document Content: {doc.file_name}",
                    content=f"Document: {doc.file_name}\n\nFull Content:\n{text}",
                    metadata={"file_name": doc.file_name, "is_full_content": True},
                )
            else:
                chunk_size = 3500
                overlap = 400
                pos = 0
                part = 1
                while pos < len(text) and part <= 8:
                    chunk_slice = text[pos:pos + chunk_size]
                    cls.index_chunk(
                        workspace=workspace,
                        source_type="document",
                        source_id=f"{doc.id}-part-{part}",
                        title=f"Document Content: {doc.file_name} (Part {part})",
                        content=f"Document: {doc.file_name} (Section {part})\n\n{chunk_slice}",
                        metadata={"file_name": doc.file_name, "part": part},
                    )
                    pos += (chunk_size - overlap)
                    part += 1

    @classmethod
    def reindex_all_workspace_documents(cls, workspace):
        """
        Ensures all DocumentAnalysis records in the workspace are indexed with up-to-date embeddings.
        """
        from .models import DocumentAnalysis
        for doc in DocumentAnalysis.objects.filter(workspace=workspace):
            cls.index_document(workspace, doc, user=doc.created_by)

    @classmethod
    def search_similar_chunks(cls, workspace, query_text, user=None, top_k=6):
        """
        Calculates cosine similarity between query and stored team memory chunks.
        Strictly enforces workspace isolation and message visibility rules.
        Includes auto-healing for legacy dimension mismatches and hybrid lexical matching.
        """
        # Auto-ensure any existing analyzed documents are indexed
        from .models import DocumentAnalysis
        if not TeamMemoryChunk.objects.filter(workspace=workspace, source_type="document").exists():
            if DocumentAnalysis.objects.filter(workspace=workspace).exists():
                cls.reindex_all_workspace_documents(workspace)

        query_vec = np.array(generate_embedding(query_text), dtype=np.float32)
        query_norm = np.linalg.norm(query_vec)

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
        # Pre-calculate query keywords for hybrid lexical scoring
        query_words = set(w.lower().strip("?,.!:;\"'") for w in query_text.split() if len(w) > 3)

        for chunk in chunks:
            # Enforce message privacy
            if chunk.source_type == "message":
                conv_id = chunk.metadata.get("conversation_id")
                if conv_id and conv_id not in [str(c) for c in allowed_conv_ids]:
                    continue

            chunk_vec = np.array(chunk.embedding, dtype=np.float32)
            # Auto-healing: If embedding dimension doesn't match current model (e.g. from previous fallback), re-embed
            if len(chunk_vec) != len(query_vec):
                try:
                    new_emb = generate_embedding(f"{chunk.title}\n{chunk.content}")
                    chunk.embedding = new_emb
                    chunk.save(update_fields=["embedding"])
                    chunk_vec = np.array(new_emb, dtype=np.float32)
                except Exception as e:
                    logger.warning(f"Failed to re-embed chunk {chunk.id}: {e}")
                    chunk_vec = np.array([], dtype=np.float32)

            similarity = 0.0
            if len(chunk_vec) == len(query_vec) and query_norm > 0:
                chunk_norm = np.linalg.norm(chunk_vec)
                if chunk_norm > 0:
                    similarity = float(np.dot(query_vec, chunk_vec) / (query_norm * chunk_norm))

            # Hybrid lexical matching boost
            content_lower = f"{chunk.title} {chunk.content}".lower()
            matched_words = [w for w in query_words if w in content_lower]
            lexical_boost = min(len(matched_words) * 0.06, 0.25)
            final_score = similarity + lexical_boost

            if final_score > 0.15 or len(matched_words) >= 2:
                scored_chunks.append((final_score, chunk))

        # Sort descending by final score
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
