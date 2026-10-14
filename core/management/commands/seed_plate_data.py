from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from core.models import User, Workspace, WorkspaceMember
from tasks.models import Project, Task, TaskActivity
from communications.models import Conversation, ConversationMember, Message
from ai_services.models import TeamMemoryChunk
from ai_services.rag_service import TeamMemoryRAGService


class Command(BaseCommand):
    help = "Seeds Plate with initial realistic demo workspace, members, tasks, and communications"

    def handle(self, *args, **options):
        self.stdout.write("Seeding Plate workspace data...")

        # 1. Users
        users_data = [
            {"username": "sourabh", "email": "saurabhsharmasg76@gmail.com", "name": "Sourabh Sharma", "role": "admin", "title": "Founder & Admin", "password": "admin", "is_staff": True, "is_superuser": True},
            {"username": "alex", "email": "alex@acme.com", "name": "Alex Chen", "role": "admin", "title": "Tech Lead", "password": "Plate123!"},
            {"username": "elena", "email": "elena@acme.com", "name": "Elena Rostova", "role": "member", "title": "Principal Designer", "password": "Plate123!"},
            {"username": "marcus", "email": "marcus@acme.com", "name": "Marcus Vance", "role": "member", "title": "Senior Backend Eng", "password": "Plate123!"},
            {"username": "priya", "email": "priya@acme.com", "name": "Priya Patel", "role": "member", "title": "Senior Frontend Eng", "password": "Plate123!"},
        ]

        users = {}
        for u in users_data:
            user, created = User.objects.get_or_create(
                username=u["username"],
                defaults={
                    "email": u["email"],
                    "name": u["name"],
                    "is_staff": u.get("is_staff", False),
                    "is_superuser": u.get("is_superuser", False),
                }
            )
            user.email = u["email"]
            user.name = u["name"]
            if u.get("is_staff"):
                user.is_staff = True
            if u.get("is_superuser"):
                user.is_superuser = True
            user.set_password(u.get("password", "Plate123!"))
            user.save()
            users[u["email"]] = (user, u["role"], u["title"])

        admin_user = users["saurabhsharmasg76@gmail.com"][0]

        # 2. Workspace
        workspace, created = Workspace.objects.get_or_create(
            name="Acme Systems",
            defaults={"owner": admin_user, "slug": "acme-systems"}
        )

        members = {}
        for email, (user, role, title) in users.items():
            member, _ = WorkspaceMember.objects.get_or_create(
                workspace=workspace,
                user=user,
                defaults={"role": role, "title": title, "status": "active"}
            )
            members[user.name] = member

        # 3. Projects
        core_proj, _ = Project.objects.get_or_create(
            workspace=workspace,
            name="Plate Core Platform",
            defaults={"description": "Main productivity platform and communications engine"}
        )
        ai_proj, _ = Project.objects.get_or_create(
            workspace=workspace,
            name="AI & Team Memory",
            defaults={"description": "Voice extraction, multimodal document analysis, and RAG memory"}
        )

        # 4. Tasks across columns
        tasks_data = [
            {
                "title": "Finalize black & white design system tokens",
                "description": "Establish crisp neutral borders, typography scale with Fustat, and blue-500 accent states.",
                "assignee": members["Elena Rostova"],
                "status": "done",
                "priority": "urgent",
                "project": core_proj,
                "labels": ["design", "ui", "foundations"],
                "deadline": timezone.now() - timedelta(days=1),
            },
            {
                "title": "Implement 2-second incremental polling for chat",
                "description": "Ensure zero WebSocket overhead. Use after_id monotonic cursors, tab visibility pause, and non-overlapping requests.",
                "assignee": members["Marcus Vance"],
                "status": "done",
                "priority": "high",
                "project": core_proj,
                "labels": ["backend", "polling", "performance"],
                "deadline": timezone.now() + timedelta(days=2),
            },
            {
                "title": "Build team member vertical stack task board",
                "description": "Horizontally scrollable member columns with persistent drag-and-drop between members and workflow statuses.",
                "assignee": members["Priya Patel"],
                "status": "in_progress",
                "priority": "high",
                "project": core_proj,
                "labels": ["frontend", "drag-and-drop", "board"],
                "deadline": timezone.now() + timedelta(days=3),
            },
            {
                "title": "Voice task extraction attribution validation",
                "description": "Ensure first-person commitments map to speaker only when attributable, otherwise leave assignee null.",
                "assignee": members["Marcus Vance"],
                "status": "in_review",
                "priority": "urgent",
                "project": ai_proj,
                "labels": ["ai", "voice", "accuracy"],
                "deadline": timezone.now() + timedelta(days=1),
            },
            {
                "title": "RAG Team Memory hybrid query synthesis",
                "description": "Combine authoritative live database records for current status with vector cosine similarity for historical decisions.",
                "assignee": members["Alex Chen"],
                "status": "in_progress",
                "priority": "high",
                "project": ai_proj,
                "labels": ["rag", "memory", "embeddings"],
                "deadline": timezone.now() + timedelta(days=4),
            },
            {
                "title": "Security audit: strictly isolate private DMs",
                "description": "Verify object-level permissions so private direct messages are inaccessible to non-participants, including workspace admins.",
                "assignee": members["Alex Chen"],
                "status": "todo",
                "priority": "urgent",
                "project": core_proj,
                "labels": ["security", "auth", "permissions"],
                "deadline": timezone.now() + timedelta(days=5),
            },
            {
                "title": "Document & screenshot OCR extraction safety",
                "description": "Treat uploaded files as untrusted content; extract clean summaries and suggested follow-up tasks without executing prompts.",
                "assignee": None,
                "status": "inbox",
                "priority": "medium",
                "project": ai_proj,
                "labels": ["security", "ai", "documents"],
                "deadline": timezone.now() + timedelta(days=7),
            },
            {
                "title": "Email notification templates for task assignments",
                "description": "Minimalist HTML email templates triggered upon task assignment, reassignment, or deadline shifts.",
                "assignee": None,
                "status": "inbox",
                "priority": "low",
                "project": core_proj,
                "labels": ["notifications", "email"],
                "deadline": timezone.now() + timedelta(days=10),
            },
        ]

        for t_spec in tasks_data:
            task, created = Task.objects.get_or_create(
                workspace=workspace,
                title=t_spec["title"],
                defaults={
                    "description": t_spec["description"],
                    "assignee": t_spec["assignee"],
                    "status": t_spec["status"],
                    "priority": t_spec["priority"],
                    "project": t_spec["project"],
                    "labels": t_spec["labels"],
                    "deadline": t_spec["deadline"],
                    "creator": admin_user,
                }
            )
            if created:
                TaskActivity.objects.create(
                    task=task,
                    actor=admin_user,
                    field_name="created",
                    old_value="",
                    new_value=task.title,
                    description=f"Created task '{task.title}'",
                )

        # 5. Conversations & Messages
        # Channels
        channels_spec = [
            ("general", "General workspace discussion and announcements"),
            ("engineering", "Architecture, code reviews, and technical execution"),
            ("design", "Design system, typography, and UX polishing"),
        ]

        channels = {}
        for name, topic in channels_spec:
            conv, _ = Conversation.objects.get_or_create(
                workspace=workspace,
                type="channel",
                name=name,
                defaults={"topic": topic, "created_by": admin_user, "is_private": False}
            )
            for u in users.values():
                ConversationMember.objects.get_or_create(conversation=conv, user=u[0])
            channels[name] = conv

        # Seed Messages in #general
        gen_messages = [
            (users["alex@acme.com"][0], "Welcome to Plate! We've kicked off our AI-native team productivity platform."),
            (users["elena@acme.com"][0], "Design system tokens are live. Fustat font is configured with ascent overrides for crisp alignment."),
            (users["marcus@acme.com"][0], "The 2-second incremental polling engine is humming smoothly. Memory footprint is minimal."),
            (users["priya@acme.com"][0], "Task board drag-and-drop looks razor sharp. Rollback handling verified."),
        ]
        for sender, text in gen_messages:
            Message.objects.get_or_create(
                conversation=channels["general"],
                sender=sender,
                content=text,
                message_type="text"
            )

        # Direct Message between Alex and Elena
        dm, _ = Conversation.objects.get_or_create(
            workspace=workspace,
            type="dm",
            is_private=True,
            created_by=admin_user,
        )
        ConversationMember.objects.get_or_create(conversation=dm, user=admin_user)
        ConversationMember.objects.get_or_create(conversation=dm, user=users["elena@acme.com"][0])
        Message.objects.get_or_create(
            conversation=dm,
            sender=admin_user,
            content="Hey Elena, can we review the contrast ratios on the member column headers?",
            message_type="text"
        )
        Message.objects.get_or_create(
            conversation=dm,
            sender=users["elena@acme.com"][0],
            content="Done! Everything uses neutral-900 typography with neutral-200 borders and subtle blue-500 indicators.",
            message_type="text"
        )

        # 6. Seed Team Memory Chunks
        TeamMemoryRAGService.index_chunk(
            workspace=workspace,
            source_type="decision",
            source_id="planning-q4-1",
            title="Postpone Complex Billing Integration",
            content="During our sprint planning, we decided to postpone the billing integration until Q1. The priority is delivering the core task board, 2-second HTTP polling chat, and voice task extraction.",
            metadata={"meeting": "Q4 Sprint Planning", "date": "2026-10-10"}
        )

        TeamMemoryRAGService.index_chunk(
            workspace=workspace,
            source_type="voice_note",
            source_id="sync-oct-12",
            title="Team Architecture Sync on HTTP Polling",
            content="Marcus and Alex agreed that WebSockets create unnecessary stateful connection complexity and reconnection issues on mobile networks. A 2-second adaptive incremental HTTP poll with after_id cursors is predictable, stateless, and rock solid.",
            metadata={"speaker": "Marcus Vance", "date": "2026-10-12"}
        )

        self.stdout.write(self.style.SUCCESS("Plate seed data successfully created!"))
        self.stdout.write("Credentials: alex@acme.com / Plate123! (Admin)")
        self.stdout.write("Members: elena@acme.com, marcus@acme.com, priya@acme.com (Password: Plate123!)")
