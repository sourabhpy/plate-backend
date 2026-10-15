import logging
import re
from django.core.mail import send_mail
from django.conf import settings
from .models import Notification
from core.models import WorkspaceMember

logger = logging.getLogger(__name__)


def extract_mentioned_users(content, workspace, actor=None):
    if not content or "@" not in content:
        return []

    members = WorkspaceMember.objects.filter(
        workspace=workspace,
        status="active"
    ).select_related("user")

    tagged_users = []
    seen_user_ids = set()
    if actor:
        seen_user_ids.add(actor.id)

    # Build pairs of (user, identifier)
    all_pairs = []
    for member in members:
        u = member.user
        if u.id in seen_user_ids:
            continue
        identifiers = set()
        if u.username:
            identifiers.add(u.username.strip())
        if u.name:
            identifiers.add(u.name.strip())
        if u.email:
            identifiers.add(u.email.strip())
            email_prefix = u.email.split("@")[0].strip()
            if email_prefix:
                identifiers.add(email_prefix)

        for ident in identifiers:
            if ident:
                all_pairs.append((u, ident))

    # Sort identifiers by length descending so longer identifiers match first (e.g. "Alex Smith" before "Alex")
    all_pairs.sort(key=lambda x: len(x[1]), reverse=True)

    matched_ranges = []
    for u, ident in all_pairs:
        if u.id in seen_user_ids:
            continue
        pattern = rf"(?<![\w])@{re.escape(ident)}(?=$|[^\w])"
        for match in re.finditer(pattern, content, re.IGNORECASE):
            start, end = match.span()
            overlaps = any(not (end <= r[0] or start >= r[1]) for r in matched_ranges)
            if not overlaps:
                matched_ranges.append((start, end))
                seen_user_ids.add(u.id)
                tagged_users.append(u)
                break

    return tagged_users


class NotificationService:
    @staticmethod
    def _send_html_email(recipient_email, subject, heading, body_text, task_title="", task_priority="", action_url=""):
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #FAFAFA; margin: 0; padding: 40px 20px; color: #111111; }}
            .container {{ max-width: 560px; margin: 0 auto; background: #FFFFFF; border: 1px solid #E5E5E5; border-radius: 8px; padding: 32px; }}
            .logo {{ font-size: 18px; font-weight: 700; letter-spacing: -0.5px; margin-bottom: 24px; color: #000000; }}
            .logo span {{ color: #3B82F6; }}
            .heading {{ font-size: 20px; font-weight: 600; margin-bottom: 12px; color: #000000; }}
            .content {{ font-size: 14px; line-height: 1.6; color: #525252; margin-bottom: 24px; }}
            .quote-card {{ background: #F9FAFB; border-left: 3px solid #3B82F6; border-radius: 0 6px 6px 0; padding: 14px 16px; margin: 16px 0; font-size: 14px; color: #1F2937; }}
            .task-card {{ background: #F9FAFB; border: 1px solid #E5E7EB; border-radius: 6px; padding: 16px; margin-bottom: 24px; }}
            .task-title {{ font-size: 15px; font-weight: 600; color: #111827; margin-bottom: 6px; }}
            .task-badge {{ display: inline-block; font-size: 11px; font-weight: 600; text-transform: uppercase; padding: 2px 8px; border-radius: 4px; background: #EFF6FF; color: #2563EB; }}
            .footer {{ font-size: 12px; color: #A3A3A3; border-top: 1px solid #F0F0F0; padding-top: 16px; text-align: center; }}
          </style>
        </head>
        <body>
          <div class="container">
            <div class="logo">Plate<span>.</span></div>
            <div class="heading">{heading}</div>
            <div class="content">{body_text}</div>
            {f'<div class="task-card"><div class="task-title">{task_title}</div><span class="task-badge">{task_priority}</span></div>' if task_title else ''}
            <div class="footer">
              Plate AI-Native Team Productivity Platform &bull; Automated notification
            </div>
          </div>
        </body>
        </html>
        """
        try:
            plain_body = body_text.replace("<br/>", "\n").replace("<br>", "\n")
            clean_plain_body = re.sub(r"<[^>]+>", "", plain_body)
            send_mail(
                subject=f"[Plate] {subject}",
                message=f"{heading}\n\n{clean_plain_body}" + (f"\n\nTask: {task_title}" if task_title else ""),
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "notifications@plate.local"),
                recipient_list=[recipient_email],
                html_message=html_content,
                fail_silently=True,
            )
        except Exception as e:
            logger.warning(f"Failed to dispatch email notification: {e}")

    @classmethod
    def notify_task_assignment(cls, task, actor, assignee, action_type="assigned"):
        title = f"Task {action_type}: {task.title}"
        message = f"{actor.name} {action_type} the task '{task.title}' to you in {task.workspace.name}."
        
        Notification.objects.create(
            workspace=task.workspace,
            recipient=assignee,
            actor=actor,
            task=task,
            notification_type="task_reassigned" if action_type == "reassigned" else "task_assigned",
            title=title,
            message=message,
        )

        cls._send_html_email(
            recipient_email=assignee.email,
            subject=title,
            heading="New Task Assignment",
            body_text=message,
            task_title=task.title,
            task_priority=task.priority,
        )

    @classmethod
    def notify_task_update(cls, task, actor, field, new_value):
        if not task.assignee:
            return

        title = f"Task {field.capitalize()} Updated: {task.title}"
        message = f"{actor.name} updated the {field} to '{new_value}' for '{task.title}'."

        Notification.objects.create(
            workspace=task.workspace,
            recipient=task.assignee.user,
            actor=actor,
            task=task,
            notification_type="deadline_changed" if field == "deadline" else "priority_changed",
            title=title,
            message=message,
        )

        cls._send_html_email(
            recipient_email=task.assignee.user.email,
            subject=title,
            heading=f"Task {field.capitalize()} Changed",
            body_text=message,
            task_title=task.title,
            task_priority=task.priority,
        )

    @classmethod
    def notify_chat_mentions(cls, workspace, actor, content, conversation_name=""):
        tagged_users = extract_mentioned_users(content, workspace, actor=actor)
        for recipient in tagged_users:
            cls.notify_chat_mention(
                workspace=workspace,
                actor=actor,
                recipient=recipient,
                message_content=content,
                conversation_name=conversation_name,
            )
        return tagged_users

    @classmethod
    def notify_chat_mention(cls, workspace, actor, recipient, message_content, conversation_name=""):
        actor_name = actor.name or actor.username or "Someone"
        title = f"{actor_name} tagged you in a chat"
        conv_info = f" in #{conversation_name}" if conversation_name else ""
        message = f"{actor_name} tagged you{conv_info}: {message_content}"

        Notification.objects.create(
            workspace=workspace,
            recipient=recipient,
            actor=actor,
            notification_type="mention",
            title=title,
            message=message,
        )

        escaped_content = (
            message_content
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br/>")
        )

        cls._send_html_email(
            recipient_email=recipient.email,
            subject=title,
            heading="You were tagged in a chat",
            body_text=f"{actor_name} tagged you in a chat message{conv_info}:<div class=\"quote-card\">{escaped_content}</div>",
        )

