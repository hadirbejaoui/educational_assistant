from django.contrib import admin

from .models import CourseDocument, DocumentChunk, DocumentPage


@admin.register(CourseDocument)
class CourseDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "file_type", "status", "uploaded_at")
    list_filter = ("file_type", "status", "owner")
    list_select_related = ("owner",)
    search_fields = ("title", "owner__username")


@admin.register(DocumentPage)
class DocumentPageAdmin(admin.ModelAdmin):
    list_display = ("document", "page_number")
    list_select_related = ("document",)


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = ("document", "chunk_index", "page_start", "page_end", "chapter", "char_count")
    list_select_related = ("document",)
    search_fields = ("document__title", "text")