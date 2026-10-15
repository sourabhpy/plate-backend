from rest_framework import status, views, permissions
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Q
from core.permissions import IsWorkspaceMember
from core.models import WorkspaceMember, User
from .models import Conversation, ConversationMember, Message
from .serializers import ConversationSerializer, MessageSerializer


class ConversationListCreateView(views.APIView):
    permission_classes = [IsWorkspaceMember]

    def get(self, request):
        # Channels in workspace (public or user is member if private)
        # Plus DMs and groups where request.user is an explicit member
        channels = Conversation.objects.filter(
            workspace=request.workspace,
            type="channel"
        )
        # Private channels require membership
        user_conversations = Conversation.objects.filter(
            workspace=request.workspace,
            members__user=request.user
        )
        visible_conversations = (channels.filter(is_private=False) | user_conversations).distinct().order_by("-updated_at")

        return Response(
            ConversationSerializer(visible_conversations, many=True, context={"request": request}).data
        )

    def post(self, request):
        conv_type = request.data.get("type", "channel")
        name = request.data.get("name", "").strip().lower()
        topic = request.data.get("topic", "").strip()
        is_private = request.data.get("is_private", False)

        if conv_type == "channel":
            if not name:
                return Response({"error": "Channel name is required"}, status=status.HTTP_400_BAD_REQUEST)
            name = name.replace(" ", "-").replace("#", "")
            
            existing = Conversation.objects.filter(
                workspace=request.workspace,
                type="channel",
                name=name
            ).first()
            if existing:
                return Response(
                    ConversationSerializer(existing, context={"request": request}).data,
                    status=status.HTTP_200_OK,
                )

            conv = Conversation.objects.create(
                workspace=request.workspace,
                type="channel",
                name=name,
                topic=topic,
                is_private=is_private,
                created_by=request.user,
            )
            ConversationMember.objects.create(conversation=conv, user=request.user)
            return Response(
                ConversationSerializer(conv, context={"request": request}).data,
                status=status.HTTP_201_CREATED,
            )

        elif conv_type == "dm":
            target_user_id = request.data.get("target_user_id")
            if not target_user_id:
                return Response({"error": "Target user ID is required for DMs"}, status=status.HTTP_400_BAD_REQUEST)
            
            target_user = get_object_or_404(User, id=target_user_id)
            
            # Ensure target is also in this workspace
            if not WorkspaceMember.objects.filter(workspace=request.workspace, user=target_user, status="active").exists():
                return Response({"error": "Target user is not in this workspace"}, status=status.HTTP_400_BAD_REQUEST)

            # Check if DM already exists between these 2 users in this workspace
            existing_dms = Conversation.objects.filter(
                workspace=request.workspace,
                type="dm",
                members__user=request.user
            ).filter(
                members__user=target_user
            ).first()

            if existing_dms:
                return Response(
                    ConversationSerializer(existing_dms, context={"request": request}).data,
                    status=status.HTTP_200_OK,
                )

            conv = Conversation.objects.create(
                workspace=request.workspace,
                type="dm",
                is_private=True,
                created_by=request.user,
            )
            ConversationMember.objects.create(conversation=conv, user=request.user)
            ConversationMember.objects.create(conversation=conv, user=target_user)
            return Response(
                ConversationSerializer(conv, context={"request": request}).data,
                status=status.HTTP_201_CREATED,
            )

        return Response({"error": "Unsupported conversation type"}, status=status.HTTP_400_BAD_REQUEST)


class ConversationDetailView(views.APIView):
    permission_classes = [IsWorkspaceMember]

    def check_access(self, conv, user):
        if conv.type == "channel" and not conv.is_private:
            return True
        return conv.members.filter(user=user).exists()

    def get(self, request, pk):
        conv = get_object_or_404(Conversation, pk=pk, workspace=request.workspace)
        if not self.check_access(conv, request.user):
            return Response({"error": "Access denied to private conversation"}, status=status.HTTP_403_FORBIDDEN)
        return Response(ConversationSerializer(conv, context={"request": request}).data)


class MessageListCreateView(views.APIView):
    """
    Message view supporting:
    - Incremental cursor-based polling (`after_id`)
    - Upward history pagination (`before_id`)
    - Initial history load (latest N messages)
    - Thread filtering (`parent_id`)
    - Posting text, audio voice messages, and file attachments
    """
    permission_classes = [IsWorkspaceMember]

    def get_conversation_and_authorize(self, conversation_id, user, workspace):
        conv = get_object_or_404(Conversation, id=conversation_id, workspace=workspace)
        if conv.type == "channel" and not conv.is_private:
            return conv
        if not conv.members.filter(user=user).exists():
            return None
        return conv

    def get(self, request, conversation_id):
        conv = self.get_conversation_and_authorize(conversation_id, request.user, request.workspace)
        if not conv:
            return Response({"error": "Access denied to private conversation"}, status=status.HTTP_403_FORBIDDEN)

        messages = Message.objects.filter(conversation=conv).select_related("sender")

        # Thread isolation: if parent_id is specified, query thread replies; otherwise top-level messages
        parent_id = request.query_params.get("parent_id")
        if parent_id:
            messages = messages.filter(parent_message_id=parent_id)
        else:
            messages = messages.filter(parent_message__isnull=True)

        after_id = request.query_params.get("after_id")
        before_id = request.query_params.get("before_id")
        limit = min(int(request.query_params.get("limit", 50)), 100)

        # 1. Incremental polling: fetch only newer messages strictly after after_id
        if after_id is not None and after_id != "":
            try:
                after_id_int = int(after_id)
                new_messages = list(messages.filter(id__gt=after_id_int).order_by("id")[:limit])
                latest_id = max([m.id for m in new_messages]) if new_messages else after_id_int
                deleted_ids = list(messages.filter(is_deleted=True).values_list("id", flat=True))
                return Response({
                    "results": MessageSerializer(new_messages, many=True, context={"request": request}).data,
                    "latest_id": latest_id,
                    "poll_cursor": latest_id,
                    "count": len(new_messages),
                    "deleted_ids": deleted_ids,
                })
            except ValueError:
                return Response({"error": "Invalid after_id"}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Older history pagination: fetch older messages strictly before before_id
        elif before_id is not None and before_id != "":
            try:
                before_id_int = int(before_id)
                older_messages = list(messages.filter(id__lt=before_id_int).order_by("-id")[:limit])
                has_more_older = len(older_messages) == limit
                # Reverse to keep chronological order
                older_messages.reverse()
                return Response({
                    "results": MessageSerializer(older_messages, many=True, context={"request": request}).data,
                    "has_more_older": has_more_older,
                    "oldest_id": older_messages[0].id if older_messages else None,
                    "count": len(older_messages),
                })
            except ValueError:
                return Response({"error": "Invalid before_id"}, status=status.HTTP_400_BAD_REQUEST)

        # 3. Initial load: latest N messages in chronological order
        else:
            latest_messages = list(messages.order_by("-id")[:limit])
            has_more_older = len(latest_messages) == limit
            latest_messages.reverse()
            latest_id = latest_messages[-1].id if latest_messages else 0
            return Response({
                "results": MessageSerializer(latest_messages, many=True, context={"request": request}).data,
                "latest_id": latest_id,
                "poll_cursor": latest_id,
                "has_more_older": has_more_older,
                "count": len(latest_messages),
            })

    def post(self, request, conversation_id):
        conv = self.get_conversation_and_authorize(conversation_id, request.user, request.workspace)
        if not conv:
            return Response({"error": "Access denied to private conversation"}, status=status.HTTP_403_FORBIDDEN)

        content = request.data.get("content", "").strip()
        message_type = request.data.get("message_type", "text")
        parent_id = request.data.get("parent_id")
        parent_message = None
        if parent_id:
            parent_message = get_object_or_404(Message, id=parent_id, conversation=conv)

        audio_file = request.FILES.get("audio_file")
        audio_duration = float(request.data.get("audio_duration", 0.0) or 0.0)

        file_obj = request.FILES.get("file")
        file_name = ""
        file_size = 0
        content_type = ""

        if audio_file:
            message_type = "audio"
        elif file_obj:
            message_type = "file"
            file_name = file_obj.name
            file_size = file_obj.size
            content_type = file_obj.content_type or ""
        elif not content:
            return Response({"error": "Message content or file is required"}, status=status.HTTP_400_BAD_REQUEST)

        message = Message.objects.create(
            conversation=conv,
            sender=request.user,
            parent_message=parent_message,
            message_type=message_type,
            content=content,
            audio_file=audio_file,
            audio_duration=audio_duration,
            file=file_obj,
            file_name=file_name,
            file_size=file_size,
            content_type=content_type,
        )

        conv.updated_at = message.created_at
        conv.save(update_fields=["updated_at"])

        # Check and notify mentioned users
        if content:
            from notifications.services import NotificationService
            conv_name = conv.name or getattr(conv, "display_name", "") or ("chat" if conv.type != "dm" else f"Direct Message")
            NotificationService.notify_chat_mentions(
                workspace=request.workspace,
                actor=request.user,
                content=content,
                conversation_name=conv_name,
            )

        return Response(
            MessageSerializer(message, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class MessageDetailView(views.APIView):
    permission_classes = [IsWorkspaceMember]

    def patch(self, request, pk):
        message = get_object_or_404(Message, id=pk, conversation__workspace=request.workspace)
        if message.sender != request.user:
            return Response({"error": "You can only edit your own messages"}, status=status.HTTP_403_FORBIDDEN)

        content = request.data.get("content")
        if content is not None:
            old_content = message.content or ""
            new_content = content.strip()
            message.content = new_content
            message.is_edited = True
            message.save()

            if new_content:
                from notifications.services import NotificationService, extract_mentioned_users
                old_mentioned_ids = {u.id for u in extract_mentioned_users(old_content, request.workspace, actor=request.user)}
                new_mentioned = extract_mentioned_users(new_content, request.workspace, actor=request.user)
                conv = message.conversation
                conv_name = conv.name or getattr(conv, "display_name", "") or ("chat" if conv.type != "dm" else "Direct Message")
                for recipient in new_mentioned:
                    if recipient.id not in old_mentioned_ids:
                        NotificationService.notify_chat_mention(
                            workspace=request.workspace,
                            actor=request.user,
                            recipient=recipient,
                            message_content=new_content,
                            conversation_name=conv_name,
                        )

        return Response(MessageSerializer(message, context={"request": request}).data)

    def delete(self, request, pk):
        message = get_object_or_404(Message, id=pk, conversation__workspace=request.workspace)
        if message.sender != request.user:
            return Response({"error": "You can only delete your own messages"}, status=status.HTTP_403_FORBIDDEN)

        message.is_deleted = True
        message.content = "This message was deleted"
        if message.audio_file:
            try:
                message.audio_file.delete(save=False)
            except Exception:
                pass
            message.audio_file = None
        if message.file:
            try:
                message.file.delete(save=False)
            except Exception:
                pass
            message.file = None
        message.save()
        return Response(MessageSerializer(message, context={"request": request}).data, status=status.HTTP_200_OK)


class MessageSearchView(views.APIView):
    permission_classes = [IsWorkspaceMember]

    def get(self, request):
        query = request.query_params.get("q", "").strip()
        if not query:
            return Response([])

        # Filter by workspace and user permissions
        visible_conv_ids = Conversation.objects.filter(
            workspace=request.workspace
        ).filter(
            Q(type="channel", is_private=False) | Q(members__user=request.user)
        ).values_list("id", flat=True)

        messages = Message.objects.filter(
            conversation_id__in=visible_conv_ids,
            content__icontains=query
        ).select_related("sender", "conversation").order_by("-id")[:30]

        return Response(MessageSerializer(messages, many=True, context={"request": request}).data)
