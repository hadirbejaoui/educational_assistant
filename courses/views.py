from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import DocumentUploadForm
from .models import CourseDocument


def _user_documents(user):
    """Seule porte d'accès aux documents : toujours filtrée par propriétaire."""
    return CourseDocument.objects.filter(owner=user)


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
            messages.success(request, f"« {document.title} » a été importé.")
            return redirect("courses:detail", pk=document.pk)
    else:
        form = DocumentUploadForm()

    return render(request, "courses/document_upload.html", {"form": form})


@login_required
def document_detail(request, pk):
    document = get_object_or_404(_user_documents(request.user), pk=pk)
    return render(request, "courses/document_detail.html", {"document": document})


@login_required
def document_delete(request, pk):
    document = get_object_or_404(_user_documents(request.user), pk=pk)
    if request.method == "POST":
        title = document.title
        document.delete()
        messages.success(request, f"« {title} » a été supprimé.")
        return redirect("courses:list")
    return render(request, "courses/document_confirm_delete.html", {"document": document})