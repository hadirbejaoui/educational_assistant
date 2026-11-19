from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import DocumentUploadForm
from .models import CourseDocument
from .services.processing import process_document
from django.conf import settings

from .services.embeddings import EmbeddingError, get_embedder, index_document
from .services.retrieval import search_chunks


def _user_documents(user):
    """Seule porte d'accès aux documents : toujours filtrée par propriétaire."""
    return CourseDocument.objects.filter(owner=user)


def _report_processing(request, document):
    if document.status == CourseDocument.Status.READY:
        messages.success(
            request,
            f"« {document.title} » analysé : {document.page_count} page(s), "
            f"{document.chunks.count()} passage(s).",
        )
    else:
        messages.warning(
            request, f"« {document.title} » : traitement échoué. {document.error_message}"
        )


@login_required
def document_list(request):
    documents = _user_documents(request.user)
    return render(request, "courses/document_list.html", {"documents": documents})


@login_required
def document_upload(request):
    if request.method == "POST":
        form = DocumentUploadForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.owner = request.user
            document.save()
            document = process_document(document)
            _report_processing(request, document)
            return redirect("courses:detail", pk=document.pk)
    else:
        form = DocumentUploadForm()

    return render(request, "courses/document_upload.html", {"form": form})


@login_required
def document_detail(request, pk):
    document = get_object_or_404(_user_documents(request.user), pk=pk)
    context = {
        "document": document,
        "chunk_count": document.chunks.count(),
        "chunks": document.chunks.all()[:10],
        "indexed_count": document.chunks.filter(
            embedding__isnull=False, embedding_model=settings.EMBEDDING_MODEL_NAME
        ).count(),
    }
    
    return render(request, "courses/document_detail.html", context)


@login_required
@require_POST
def document_reprocess(request, pk):
    document = get_object_or_404(_user_documents(request.user), pk=pk)
    document = process_document(document)
    _report_processing(request, document)
    return redirect("courses:detail", pk=document.pk)


@login_required
def document_delete(request, pk):
    document = get_object_or_404(_user_documents(request.user), pk=pk)
    if request.method == "POST":
        title = document.title
        document.delete()
        messages.success(request, f"« {title} » a été supprimé.")
        return redirect("courses:list")
    return render(request, "courses/document_confirm_delete.html", {"document": document})
@login_required
@require_POST
def document_index(request, pk):
    document = get_object_or_404(_user_documents(request.user), pk=pk)
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
    document = get_object_or_404(_user_documents(request.user), pk=pk)
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