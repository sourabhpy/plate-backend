from rest_framework import status, views, permissions
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from core.permissions import IsWorkspaceMember
from .models import Notification
from .serializers import NotificationSerializer


class NotificationListView(views.APIView):
    permission_classes = [IsWorkspaceMember]

    def get(self, request):
        notifications = Notification.objects.filter(
            workspace=request.workspace,
            recipient=request.user
        ).select_related("actor", "task")[:50]
        unread_count = Notification.objects.filter(
            workspace=request.workspace,
            recipient=request.user,
            is_read=False
        ).count()
        return Response({
            "results": NotificationSerializer(notifications, many=True).data,
            "unread_count": unread_count,
        })


class NotificationMarkReadView(views.APIView):
    permission_classes = [IsWorkspaceMember]

    def post(self, request, pk=None):
        if pk:
            notification = get_object_or_404(
                Notification,
                pk=pk,
                workspace=request.workspace,
                recipient=request.user
            )
            notification.is_read = True
            notification.save(update_fields=["is_read"])
            return Response(NotificationSerializer(notification).data)
        else:
            # Mark all as read
            Notification.objects.filter(
                workspace=request.workspace,
                recipient=request.user,
                is_read=False
            ).update(is_read=True)
            return Response({"success": True})
