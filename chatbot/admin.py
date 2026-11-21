from django.contrib import admin

from .models import ChatMessage, Conversation


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "document", "updated_at")
    list_filter = ("owner",)
    list_select_related = ("owner", "document")
    search_fields = ("title", "owner__username", "document__title")


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("conversation", "role", "is_grounded", "created_at")
    list_filter = ("role", "is_grounded")
    list_select_related = ("conversation",)
