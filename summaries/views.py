import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.pagination import paginate
from core.ratelimit import rate_limit
from courses.models import CourseDocument

from .models import Summary
from .services.errors import SummaryError
from .services.summarization import generate_summary

logger = logging.getLogger(__name__)


def _user_documents(user):
    return CourseDocument.objects.filter(owner=user)


@login_required
def summary_list(request):
    summaries = paginate(
        request,
        Summary.objects.filter(document__owner=request.user).select_related("document"),
    )
    return render(request, "summaries/summary_list.html", {"summaries": summaries})


@login_required
def document_summaries(request, pk):
    document = get_object_or_404(_user_documents(request.user), pk=pk)
    existing = {s.level: s for s in document.summaries.all()}
    levels = [
        {"value": value, "label": label, "summary": existing.get(value)}
        for value, label in Summary.Level.choices
    ]
    return render(
        request,
        "summaries/document_summaries.html",
        {"document": document, "levels": levels},
    )


@login_required
@require_POST
@rate_limit("summary")
def summary_generate(request, pk, level):
    if level not in Summary.Level.values:
        raise Http404("Niveau inconnu.")
    document = get_object_or_404(_user_documents(request.user), pk=pk)

    if document.status != CourseDocument.Status.READY:
        messages.error(request, "Le document n'est pas encore prêt pour être résumé.")
        return redirect("summaries:document", pk=document.pk)

    try:
        generate_summary(document, level)
        messages.success(request, "Résumé généré.")
    except SummaryError as exc:
        messages.warning(request, str(exc))
    except Exception:
        logger.exception("Échec du résumé du document %s", document.pk)
        messages.error(request, "Erreur inattendue pendant la génération du résumé.")
    return redirect("summaries:document", pk=document.pk)