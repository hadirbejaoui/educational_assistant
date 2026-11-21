from django.contrib import admin

from .models import Choice, Question, Quiz, QuizAttempt


class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 0


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("quiz", "order", "difficulty")
    list_select_related = ("quiz",)
    inlines = [ChoiceInline]


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "document", "difficulty", "provider", "created_at")
    list_filter = ("difficulty", "owner")
    list_select_related = ("owner", "document")
    search_fields = ("title", "owner__username", "document__title")


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ("quiz", "user", "score", "total", "completed_at")
    list_filter = ("user",)
    list_select_related = ("quiz", "user")