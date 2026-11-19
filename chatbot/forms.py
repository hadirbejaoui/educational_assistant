from django import forms

from accounts.forms import StyledFormMixin
from courses.models import CourseDocument


class NewConversationForm(StyledFormMixin, forms.Form):
    document = forms.ModelChoiceField(queryset=CourseDocument.objects.none(), label="Cours")

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Seuls les documents prêts de l'utilisateur sont proposés
        self.fields["document"].queryset = CourseDocument.objects.filter(
            owner=user, status=CourseDocument.Status.READY
        )