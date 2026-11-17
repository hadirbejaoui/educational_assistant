import os

from django import forms

from accounts.forms import StyledFormMixin

from .models import CourseDocument
from .validators import validate_document_file


class DocumentUploadForm(StyledFormMixin, forms.ModelForm):
    file = forms.FileField(
        label="Fichier (PDF ou TXT)",
        validators=[validate_document_file],
        widget=forms.ClearableFileInput(attrs={"accept": ".pdf,.txt"}),
    )

    class Meta:
        model = CourseDocument
        fields = ("title", "file")
        labels = {"title": "Titre du cours"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].required = False  # sinon, on prend le nom du fichier

    def save(self, commit=True):
        document = super().save(commit=False)
        uploaded = self.cleaned_data["file"]
        extension = os.path.splitext(uploaded.name)[1].lower().lstrip(".")
        document.file_type = extension
        document.file_size = uploaded.size
        if not document.title:
            document.title = os.path.splitext(uploaded.name)[0][:255]
        if commit:
            document.save()
        return document