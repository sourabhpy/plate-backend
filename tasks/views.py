from rest_framework import status, views, permissions
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Q
from core.permissions import IsWorkspaceMember
from core.models import WorkspaceMember
from .models import Project, Task, TaskActivity, TaskAttachment
from .serializers import (
    ProjectSerializer,
    TaskSerializer,
    TaskAttachmentSerializer,
)
from notifications.services import NotificationService
from core.media_validators import validate_max_file_size, validate_not_video


class ProjectListCreateView(views.APIView):
    permission_classes = [IsWorkspaceMember]

    def get(self, request):
        projects = Project.objects.filter(workspace=request.workspace).order_by("-created_at")
        return Response(ProjectSerializer(projects, many=True).data)

    def post(self, request):
        name = request.data.get("name")
        if not name:
            return Response({"error": "Project name is required"}, status=status.HTTP_400_BAD_REQUEST)
        description = request.data.get("description", "")
        project = Project.objects.create(
            workspace=request.workspace,
            name=name,
            description=description,
        )
        return Response(ProjectSerializer(project).data, status=status.HTTP_201_CREATED)


class TaskListCreateView(views.APIView):
    permission_classes = [IsWorkspaceMember]

    def get(self, request):
        tasks = Task.objects.filter(workspace=request.workspace).select_related(
            "assignee__user", "creator", "project"
        ).prefetch_related("attachments", "activities__actor")

        # Filters
        assignee_param = request.query_params.get("assignee")
        if assignee_param == "me":
            tasks = tasks.filter(assignee__user=request.user)
        elif assignee_param == "unassigned":
            tasks = tasks.filter(assignee__isnull=True)
        elif assignee_param:
            tasks = tasks.filter(assignee_id=assignee_param)

        status_param = request.query_params.get("status")
        if status_param:
            tasks = tasks.filter(status=status_param)

        priority_param = request.query_params.get("priority")
        if priority_param:
            tasks = tasks.filter(priority=priority_param)

        project_param = request.query_params.get("project")
        if project_param:
            tasks = tasks.filter(project_id=project_param)

        search_query = request.query_params.get("search")
        if search_query:
            tasks = tasks.filter(
                Q(title__icontains=search_query) | Q(description__icontains=search_query)
            )

        return Response(TaskSerializer(tasks, many=True, context={"request": request}).data)

    def post(self, request):
        title = request.data.get("title")
        if not title:
            return Response({"error": "Title is required"}, status=status.HTTP_400_BAD_REQUEST)

        description = request.data.get("description", "")
        status_val = request.data.get("status", "inbox")
        priority_val = request.data.get("priority", "medium")
        deadline_val = request.data.get("deadline") or None
        labels = request.data.get("labels", [])
        if isinstance(labels, str):
            labels = [l.strip() for l in labels.split(",") if l.strip()]

        project_id = request.data.get("project_id")
        project = None
        if project_id:
            project = Project.objects.filter(id=project_id, workspace=request.workspace).first()

        assignee = None
        assignee_id = request.data.get("assignee_id")
        if assignee_id and assignee_id != "unassigned":
            assignee = WorkspaceMember.objects.filter(id=assignee_id, workspace=request.workspace).first()

        source_type = request.data.get("source_type", "manual")
        source_id = request.data.get("source_id", "")
        evidence_quote = request.data.get("evidence_quote", "")

        task = Task.objects.create(
            workspace=request.workspace,
            project=project,
            title=title,
            description=description,
            assignee=assignee,
            creator=request.user,
            status=status_val,
            priority=priority_val,
            deadline=deadline_val,
            labels=labels,
            source_type=source_type,
            source_id=source_id,
            evidence_quote=evidence_quote,
        )

        TaskActivity.objects.create(
            task=task,
            actor=request.user,
            field_name="created",
            old_value="",
            new_value=task.title,
            description=f"Created task '{task.title}'",
        )

        # Notify assignee if created by admin or another user
        if assignee and assignee.user != request.user:
            NotificationService.notify_task_assignment(
                task=task,
                actor=request.user,
                assignee=assignee.user,
                action_type="assigned"
            )

        return Response(
            TaskSerializer(task, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class TaskDetailView(views.APIView):
    permission_classes = [IsWorkspaceMember]

    def get_task(self, pk, workspace):
        return get_object_or_404(
            Task.objects.select_related("assignee__user", "creator", "project").prefetch_related(
                "attachments", "activities__actor"
            ),
            pk=pk,
            workspace=workspace,
        )

    def get(self, request, pk):
        task = self.get_task(pk, request.workspace)
        return Response(TaskSerializer(task, context={"request": request}).data)

    def patch(self, request, pk):
        task = self.get_task(pk, request.workspace)
        data = request.data

        old_status = task.status
        old_priority = task.priority
        old_deadline = task.deadline
        old_assignee = task.assignee

        # Update title & description
        if "title" in data and data["title"] != task.title:
            TaskActivity.objects.create(
                task=task,
                actor=request.user,
                field_name="title",
                old_value=task.title,
                new_value=data["title"],
                description=f"Renamed task to '{data['title']}'",
            )
            task.title = data["title"]

        if "description" in data and data["description"] != task.description:
            TaskActivity.objects.create(
                task=task,
                actor=request.user,
                field_name="description",
                old_value="",
                new_value="",
                description="Updated description",
            )
            task.description = data["description"]

        if "status" in data and data["status"] != old_status:
            TaskActivity.objects.create(
                task=task,
                actor=request.user,
                field_name="status",
                old_value=old_status,
                new_value=data["status"],
                description=f"Moved status from {old_status} to {data['status']}",
            )
            task.status = data["status"]

        if "priority" in data and data["priority"] != old_priority:
            TaskActivity.objects.create(
                task=task,
                actor=request.user,
                field_name="priority",
                old_value=old_priority,
                new_value=data["priority"],
                description=f"Changed priority to {data['priority']}",
            )
            task.priority = data["priority"]
            if task.assignee and task.assignee.user != request.user:
                NotificationService.notify_task_update(
                    task=task,
                    actor=request.user,
                    field="priority",
                    new_value=data["priority"]
                )

        if "deadline" in data:
            new_deadline = data["deadline"] or None
            if str(new_deadline) != str(old_deadline):
                TaskActivity.objects.create(
                    task=task,
                    actor=request.user,
                    field_name="deadline",
                    old_value=str(old_deadline or ""),
                    new_value=str(new_deadline or ""),
                    description="Updated deadline",
                )
                task.deadline = new_deadline
                if task.assignee and task.assignee.user != request.user:
                    NotificationService.notify_task_update(
                        task=task,
                        actor=request.user,
                        field="deadline",
                        new_value=str(new_deadline)
                    )

        if "assignee_id" in data:
            new_assignee_id = data["assignee_id"]
            if new_assignee_id in [None, "", "unassigned"]:
                if old_assignee is not None:
                    TaskActivity.objects.create(
                        task=task,
                        actor=request.user,
                        field_name="assignee",
                        old_value=old_assignee.user.name,
                        new_value="Unassigned",
                        description=f"Unassigned task from {old_assignee.user.name}",
                    )
                task.assignee = None
            else:
                new_assignee = WorkspaceMember.objects.filter(
                    id=new_assignee_id, workspace=request.workspace
                ).first()
                if new_assignee and new_assignee != old_assignee:
                    TaskActivity.objects.create(
                        task=task,
                        actor=request.user,
                        field_name="assignee",
                        old_value=old_assignee.user.name if old_assignee else "Unassigned",
                        new_value=new_assignee.user.name,
                        description=f"Reassigned task to {new_assignee.user.name}",
                    )
                    task.assignee = new_assignee
                    if new_assignee.user != request.user:
                        NotificationService.notify_task_assignment(
                            task=task,
                            actor=request.user,
                            assignee=new_assignee.user,
                            action_type="reassigned" if old_assignee else "assigned",
                        )

        if "labels" in data:
            task.labels = data["labels"]

        if "project_id" in data:
            project_id = data["project_id"]
            task.project = Project.objects.filter(id=project_id, workspace=request.workspace).first() if project_id else None

        task.save()
        return Response(TaskSerializer(task, context={"request": request}).data)

    def delete(self, request, pk):
        task = self.get_task(pk, request.workspace)
        task.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TaskMoveView(views.APIView):
    """
    Dedicated endpoint for fast, persistent drag-and-drop operations across columns (members and/or statuses).
    """
    permission_classes = [IsWorkspaceMember]

    def patch(self, request, pk):
        task = get_object_or_404(Task, pk=pk, workspace=request.workspace)
        new_status = request.data.get("status")
        new_assignee_id = request.data.get("assignee_id")
        position = request.data.get("position")

        if new_status and new_status in dict(Task.STATUS_CHOICES):
            if task.status != new_status:
                TaskActivity.objects.create(
                    task=task,
                    actor=request.user,
                    field_name="status",
                    old_value=task.status,
                    new_value=new_status,
                    description=f"Moved to {new_status} via drag-and-drop",
                )
                task.status = new_status

        if "assignee_id" in request.data:
            old_assignee = task.assignee
            if new_assignee_id in [None, "", "unassigned"]:
                if old_assignee:
                    TaskActivity.objects.create(
                        task=task,
                        actor=request.user,
                        field_name="assignee",
                        old_value=old_assignee.user.name,
                        new_value="Unassigned",
                        description="Unassigned via drag-and-drop",
                    )
                    task.assignee = None
            else:
                new_assignee = WorkspaceMember.objects.filter(
                    id=new_assignee_id, workspace=request.workspace
                ).first()
                if new_assignee and new_assignee != old_assignee:
                    TaskActivity.objects.create(
                        task=task,
                        actor=request.user,
                        field_name="assignee",
                        old_value=old_assignee.user.name if old_assignee else "Unassigned",
                        new_value=new_assignee.user.name,
                        description=f"Assigned to {new_assignee.user.name} via drag-and-drop",
                    )
                    task.assignee = new_assignee
                    if new_assignee.user != request.user:
                        NotificationService.notify_task_assignment(
                            task=task,
                            actor=request.user,
                            assignee=new_assignee.user,
                            action_type="reassigned" if old_assignee else "assigned",
                        )

        if position is not None:
            try:
                task.position = int(position)
            except (ValueError, TypeError):
                pass

        task.save()
        return Response(TaskSerializer(task, context={"request": request}).data)


class TaskAttachmentUploadView(views.APIView):
    permission_classes = [IsWorkspaceMember]

    def post(self, request, pk):
        task = get_object_or_404(Task, pk=pk, workspace=request.workspace)
        file_obj = request.FILES.get("file")
        if not file_obj:
            return Response({"error": "File is required"}, status=status.HTTP_400_BAD_REQUEST)

        is_not_video, video_err = validate_not_video(file_obj)
        if not is_not_video:
            return Response({"error": video_err}, status=status.HTTP_400_BAD_REQUEST)

        is_valid_size, size_err = validate_max_file_size(file_obj, label="Attachment file")
        if not is_valid_size:
            return Response({"error": size_err}, status=status.HTTP_400_BAD_REQUEST)

        attachment = TaskAttachment.objects.create(
            task=task,
            uploader=request.user,
            file=file_obj,
            file_name=file_obj.name,
            file_size=file_obj.size,
            content_type=file_obj.content_type or "",
        )

        TaskActivity.objects.create(
            task=task,
            actor=request.user,
            field_name="attachment",
            old_value="",
            new_value=file_obj.name,
            description=f"Attached file '{file_obj.name}'",
        )

        return Response(
            TaskAttachmentSerializer(attachment, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )
