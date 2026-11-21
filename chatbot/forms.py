from django import forms

from accounts.forms import StyledFormMixin
from core.permissions import user_documents
from courses.models import CourseDocument


class NewConversationForm(StyledFormMixin, forms.Form):
    document = forms.ModelChoiceField(queryset=CourseDocument.objects.none(), label="Cours")

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Seuls les cours prêts de l'utilisateur sont proposés (un autre identifiant est refusé)
        self.fields["document"].queryset = user_documents(user).filter(
            status=CourseDocument.Status.READY
        )