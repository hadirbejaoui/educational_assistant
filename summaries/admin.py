from django.contrib import admin

from .models import Summary


@admin.register(Summary)
class SummaryAdmin(admin.ModelAdmin):
    list_display = ("document", "owner", "level", "provider", "section_count", "updated_at")
    list_filter = ("level", "provider")
    list_select_related = ("document__owner",)
    search_fields = ("document__title", "document__owner__username")

    @admin.display(description="propriétaire", ordering="document__owner__username")
    def owner(self, summary):
        return summary.document.owner