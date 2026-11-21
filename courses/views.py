import mimetypes

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.pagination import paginate
from core.permissions import user_documents

from .forms import DocumentUploadForm
from .models import CourseDocument
from .services.embeddings import EmbeddingError, get_embedder, index_document
from .services.processing import process_document
from .services.retrieval import search_chunks


def _process_and_index(request, document):
    """Analyse le fichier puis indexe ses passages, et rend compte du résultat."""
    document = process_document(document)
    if document.status != CourseDocument.Status.READY:
        messages.warning(
            request, f"« {document.title} » : traitement échoué. {document.error_message}"
        )
        return document
    summary = (
        f"« {document.title} » analysé : {document.page_count} page(s), "
        f"{document.chunks.count()} passage(s)"
    )
    try:
        index_document(document, get_embedder())
    except EmbeddingError as exc:
        # Le cours reste utilisable (résumés, quiz) ; l'index sera recalculé plus tard
        messages.warning(request, f"{summary}, mais pas encore indexé : {exc}")
    else:
        messages.success(request, f"{summary}, indexé pour le chatbot.")
    return document


@login_required
def document_list(request):
    documents = paginate(request, user_documents(request.user))
    return render(request, "courses/document_list.html", {"documents": documents})


@login_required
def document_upload(request):
    if request.method == "POST":
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.owner = request.user
            document.save()
            document = _process_and_index(request, document)
            return redirect("courses:detail", pk=document.pk)
    else:
        form = DocumentUploadForm()

    return render(
        request,
        "courses/document_upload.html",
        {"form": form, "max_mb": settings.MAX_UPLOAD_SIZE_MB},
    )


@login_required
def document_detail(request, pk):
    document = get_object_or_404(user_documents(request.user), pk=pk)
    context = {
        "document": document,
        "chunk_count": document.chunks.count(),
        "chunks": document.chunks.all()[:10],
        "indexed_count": document.chunks.filter(
            embedding__isnull=False, embedding_model=settings.EMBEDDING_MODEL_NAME
        ).count(),
        "summary_count": document.summaries.count(),
        "quiz_count": document.quizzes.count(),
        "conversation_count": document.conversations.count(),
    }
    return render(request, "courses/document_detail.html", context)


@login_required
@require_POST
def document_reprocess(request, pk):
    document = get_object_or_404(user_documents(request.user), pk=pk)
    document = _process_and_index(request, document)
    return redirect("courses:detail", pk=document.pk)


@login_required
def document_delete(request, pk):
    document = get_object_or_404(user_documents(request.user), pk=pk)
    if request.method == "POST":
        title = document.title
        document.delete()
        messages.success(request, f"« {title} » a été supprimé.")
        return redirect("courses:list")
    return render(request, "courses/document_confirm_delete.html", {"document": document})


@login_required
@require_POST
def document_index(request, pk):
    document = get_object_or_404(user_documents(request.user), pk=pk)
    if document.status != CourseDocument.Status.READY:
        messages.error(request, "Le document n'est pas prêt pour l'indexation.")
        return redirect("courses:detail", pk=document.pk)
    try:
        count = index_document(document, get_embedder())
        messages.success(request, f"{count} passage(s) indexé(s).")
    except EmbeddingError as exc:
        messages.warning(request, str(exc))
    return redirect("courses:detail", pk=document.pk)


@login_required
def document_search(request, pk):
    document = get_object_or_404(user_documents(request.user), pk=pk)
    query = request.GET.get("q", "").strip()
    hits = []
    if query:
        try:
            hits = search_chunks(document, query, embedder=get_embedder())
        except EmbeddingError as exc:
            messages.warning(request, str(exc))
    return render(
        request,
        "courses/document_search.html",
        {"document": document, "query": query, "hits": hits},
    )


@login_required
def document_file(request, pk):
    """Sert le fichier original, uniquement à son propriétaire (404 pour les autres)."""
    document = get_object_or_404(user_documents(request.user), pk=pk)
    try:
        handle = document.file.open("rb")
    except (FileNotFoundError, ValueError):
        raise Http404("Fichier introuvable.")
    extension = "." + document.file_type
    content_type = mimetypes.types_map.get(extension, "application/octet-stream")
    if document.file_type == "txt":
        content_type = "text/plain; charset=utf-8"
    response = FileResponse(handle, content_type=content_type, filename=f"{document.title}{extension}")
    response["Cache-Control"] = "private, no-store"  # jamais conservé par un cache partagé
    return response
