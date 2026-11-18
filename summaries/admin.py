from django.contrib import admin

from .models import Summary


@admin.register(Summary)
class SummaryAdmin(admin.ModelAdmin):
    list_display = ("document", "level", "provider", "section_count", "updated_at")
    list_filter = ("level", "provider")
    list_select_related = ("document",)