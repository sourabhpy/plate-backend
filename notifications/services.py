import logging
from django.core.mail import send_mail
from django.conf import settings
from .models import Notification

logger = logging.getLogger(__name__)


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
            send_mail(
                subject=f"[Plate] {subject}",
                message=f"{heading}\n\n{body_text}\n\nTask: {task_title}",
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
