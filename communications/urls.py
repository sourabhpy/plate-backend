from django.urls import path
from .views import (
    ConversationListCreateView,
    ConversationDetailView,
    MessageListCreateView,
    MessageDetailView,
    MessageSearchView,
)

urlpatterns = [
    path("conversations/", ConversationListCreateView.as_view(), name="conversation-list-create"),
    path("conversations/<uuid:pk>/", ConversationDetailView.as_view(), name="conversation-detail"),
    path("conversations/<uuid:conversation_id>/messages/", MessageListCreateView.as_view(), name="message-list-create"),
    path("messages/<int:pk>/", MessageDetailView.as_view(), name="message-detail"),
    path("search/", MessageSearchView.as_view(), name="message-search"),
]
