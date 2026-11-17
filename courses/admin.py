from django.contrib import admin

from .models import CourseDocument, DocumentPage


@admin.register(CourseDocument)
class CourseDocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "file_type", "status", "uploaded_at")
    list_filter = ("file_type", "status")
    search_fields = ("title", "owner__username")


@admin.register(DocumentPage)
class DocumentPageAdmin(admin.ModelAdmin):
    list_display = ("document", "page_number")