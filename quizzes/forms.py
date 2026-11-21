from django import forms
from django.conf import settings

from accounts.forms import StyledFormMixin
from core.permissions import user_documents
from courses.models import CourseDocument

from .models import Quiz


class QuizCreateForm(StyledFormMixin, forms.Form):
    document = forms.ModelChoiceField(queryset=CourseDocument.objects.none(), label="Cours")
    count = forms.IntegerField(label="Nombre de questions", min_value=1, initial=5)
    difficulty = forms.ChoiceField(
        label="Difficulté", choices=Quiz.Difficulty.choices, initial="medium"
    )

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Seuls les cours prêts de l'utilisateur sont proposés (un autre identifiant est refusé)
        self.fields["document"].queryset = user_documents(user).filter(
            status=CourseDocument.Status.READY
        )
        self.fields["count"].max_value = settings.QUIZ_MAX_QUESTIONS
        self.fields["count"].widget.attrs["max"] = settings.QUIZ_MAX_QUESTIONS

    def clean_count(self):
        count = self.cleaned_data["count"]
        if count > settings.QUIZ_MAX_QUESTIONS:
            raise forms.ValidationError(
                f"Maximum {settings.QUIZ_MAX_QUESTIONS} questions."
            )
        return count