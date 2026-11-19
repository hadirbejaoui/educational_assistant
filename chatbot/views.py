import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from courses.services.embeddings import EmbeddingError, get_embedder, index_document
from llm import LLMError

from .forms import NewConversationForm
from .models import ChatMessage, Conversation
from .services.errors import RagError
from .services.rag import answer_question

logger = logging.getLogger(__name__)


def _user_conversations(user):
    return Conversation.objects.filter(document__owner=user)


@login_required
def conversation_list(request):
    conversations = _user_conversations(request.user).select_related("document")
    form = NewConversationForm(request.user, initial={"document": request.GET.get("document")})
    return render(
        request,
        "chatbot/conversation_list.html",
        {"conversations": conversations, "form": form},
    )


@login_required
@require_POST
def conversation_create(request):
    form = NewConversationForm(request.user, request.POST)
    if not form.is_valid():
        messages.error(request, "Choisissez un de vos cours prêts.")
        return redirect("chatbot:list")

    document = form.cleaned_data["document"]
    try:
        # Indexe seulement les passages qui n'ont pas encore de vecteur
        index_document(document, get_embedder())
    except EmbeddingError as exc:
        messages.error(request, str(exc))
        return redirect("chatbot:list")

    conversation = Conversation.objects.create(
        document=document, title=f"Discussion - {document.title}"[:255]
    )
    return redirect("chatbot:detail", pk=conversation.pk)


@login_required
def conversation_detail(request, pk):
    conversation = get_object_or_404(
        _user_conversations(request.user).select_related("document"), pk=pk
    )
    # « chat_messages » et non « messages » : ce nom est pris par le framework de messages
    return render(
        request,
        "chatbot/conversation_detail.html",
        {
            "conversation": conversation,
            "chat_messages": conversation.messages.all(),
            "max_chars": settings.RAG_MAX_QUESTION_CHARS,
        },
    )


@login_required
@require_POST
def conversation_send(request, pk):
    conversation = get_object_or_404(
        _user_conversations(request.user).select_related("document"), pk=pk
    )
    question = request.POST.get("message", "").strip()
    if not question:
        return JsonResponse({"error": "Écrivez une question."}, status=400)
    if len(question) > settings.RAG_MAX_QUESTION_CHARS:
        return JsonResponse(
            {"error": f"Question trop longue (maximum {settings.RAG_MAX_QUESTION_CHARS} caractères)."},
            status=400,
        )

    is_first = not conversation.messages.exists()
    try:
        answer = answer_question(conversation, question)
    except (RagError, LLMError, EmbeddingError) as exc:
        return JsonResponse({"error": str(exc)}, status=502)
    except Exception:
        logger.exception("Échec du chatbot pour la conversation %s", conversation.pk)
        return JsonResponse(
            {"error": "Erreur inattendue pendant la génération de la réponse."}, status=500
        )

    # On n'enregistre qu'une fois la réponse obtenue : pas de question orpheline
    with transaction.atomic():
        ChatMessage.objects.create(
            conversation=conversation, role=ChatMessage.Role.USER, content=question
        )
        ChatMessage.objects.create(
            conversation=conversation,
            role=ChatMessage.Role.ASSISTANT,
            content=answer.content,
            sources=answer.sources,
            is_grounded=answer.grounded,
        )
        if is_first:
            conversation.title = question[:80]
        conversation.save(update_fields=["title", "updated_at"])

    return JsonResponse(
        {"answer": answer.content, "sources": answer.sources, "grounded": answer.grounded}
    )


@login_required
@require_POST
def conversation_delete(request, pk):
    conversation = get_object_or_404(_user_conversations(request.user), pk=pk)
    conversation.delete()
    messages.success(request, "Conversation supprimée.")
    return redirect("chatbot:list")