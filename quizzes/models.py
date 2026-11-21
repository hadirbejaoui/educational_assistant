from django.conf import settings
from django.db import models

from courses.models import CourseDocument


class Quiz(models.Model):
    class Difficulty(models.TextChoices):
        EASY = "easy", "Facile"
        MEDIUM = "medium", "Moyen"
        HARD = "hard", "Difficile"

    document = models.ForeignKey(
        CourseDocument, on_delete=models.CASCADE, related_name="quizzes"
    )
    # Les cours sont partagés ; chaque étudiant a ses propres quiz
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quizzes"
    )
    title = models.CharField(max_length=255)
    difficulty = models.CharField(max_length=10, choices=Difficulty.choices)
    provider = models.CharField(max_length=50)
    model_name = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["document", "-created_at"])]

    def __str__(self):
        return self.title


class Question(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="questions")
    order = models.PositiveIntegerField()
    text = models.TextField()
    explanation = models.TextField()
    difficulty = models.CharField(max_length=10, choices=Quiz.Difficulty.choices)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["quiz", "order"], name="unique_question_order")
        ]

    def __str__(self):
        return f"Q{self.order} - {self.quiz.title}"


class Choice(models.Model):
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="choices"
    )
    order = models.PositiveIntegerField()
    text = models.TextField()
    is_correct = models.BooleanField(default=False)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["question", "order"], name="unique_choice_order"),
            # Une seule bonne réponse par question, garantie par la base de données
            models.UniqueConstraint(
                fields=["question"],
                condition=models.Q(is_correct=True),
                name="one_correct_choice_per_question",
            ),
        ]

    def __str__(self):
        return self.text[:50]


class QuizAttempt(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name="attempts")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quiz_attempts"
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    score = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-started_at"]

    @property
    def grade_out_of_20(self):
        return round(self.score / self.total * 20, 1) if self.total else 0

    @property
    def percent(self):
        return round(self.score / self.total * 100) if self.total else 0

    def __str__(self):
        return f"{self.quiz.title} - {self.score}/{self.total}"


class StudentAnswer(models.Model):
    attempt = models.ForeignKey(
        QuizAttempt, on_delete=models.CASCADE, related_name="answers"
    )
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name="+")
    selected_choice = models.ForeignKey(
        Choice, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    is_correct = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["attempt", "question"], name="one_answer_per_question"
            )
        ]