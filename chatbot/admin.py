from django.contrib import admin

from .models import ChatMessage, Conversation


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("title", "document", "updated_at")
    list_select_related = ("document",)


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("conversation", "role", "is_grounded", "created_at")
    list_select_related = ("conversation",)