import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from llm import LLMError

from .forms import QuizCreateForm
from .models import Quiz, QuizAttempt
from .services.errors import QuizError
from .services.generation import generate_quiz
from .services.grading import grade_attempt

logger = logging.getLogger(__name__)


def _user_quizzes(user):
    return Quiz.objects.filter(document__owner=user)


@login_required
def quiz_list(request):
    quizzes = (
        _user_quizzes(request.user)
        .select_related("document")
        .annotate(question_count=Count("questions"))
    )
    return render(request, "quizzes/quiz_list.html", {"quizzes": quizzes})


@login_required
def quiz_create(request):
    if request.method == "POST":
        form = QuizCreateForm(request.user, request.POST)
        if form.is_valid():
            try:
                quiz = generate_quiz(
                    form.cleaned_data["document"],
                    form.cleaned_data["count"],
                    form.cleaned_data["difficulty"],
                )
            except (QuizError, LLMError) as exc:
                messages.error(request, str(exc))
            except Exception:
                logger.exception("Échec de la génération du quiz")
                messages.error(request, "Erreur inattendue pendant la génération du quiz.")
            else:
                messages.success(request, f"Quiz généré : {quiz.questions.count()} question(s).")
                return redirect("quizzes:detail", pk=quiz.pk)
    else:
        form = QuizCreateForm(request.user, initial={"document": request.GET.get("document")})
    return render(request, "quizzes/quiz_create.html", {"form": form})


@login_required
def quiz_detail(request, pk):
    quiz = get_object_or_404(
        _user_quizzes(request.user).select_related("document"), pk=pk
    )
    attempts = quiz.attempts.filter(completed_at__isnull=False)
    return render(
        request,
        "quizzes/quiz_detail.html",
        {"quiz": quiz, "attempts": attempts, "question_count": quiz.questions.count()},
    )


@login_required
def quiz_take(request, pk):
    quiz = get_object_or_404(_user_quizzes(request.user), pk=pk)
    if request.method == "POST":
        selections = {}
        for key, value in request.POST.items():
            if key.startswith("question_") and key[9:].isdigit() and value.isdigit():
                selections[int(key[9:])] = int(value)
        attempt = grade_attempt(quiz, selections)
        return redirect("quizzes:result", pk=attempt.pk)
    questions = quiz.questions.prefetch_related("choices")
    return render(request, "quizzes/quiz_take.html", {"quiz": quiz, "questions": questions})


@login_required
def attempt_result(request, pk):
    attempt = get_object_or_404(
        QuizAttempt.objects.filter(quiz__document__owner=request.user).select_related("quiz"),
        pk=pk,
    )
    answers = attempt.answers.select_related("question", "selected_choice").prefetch_related(
        "question__choices"
    ).order_by("question__order")
    return render(request, "quizzes/quiz_result.html", {"attempt": attempt, "answers": answers})


@login_required
@require_POST
def quiz_delete(request, pk):
    quiz = get_object_or_404(_user_quizzes(request.user), pk=pk)
    quiz.delete()
    messages.success(request, "Quiz supprimé.")
    return redirect("quizzes:list")