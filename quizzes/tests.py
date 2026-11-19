import json
import shutil
import tempfile
from unittest.mock import patch
from llm import LLMError, get_llm_client
from llm.ollama import _strip_reasoning

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from courses.models import CourseDocument, DocumentChunk
from llm.base import BaseLLMClient

from .models import Choice, Quiz, QuizAttempt
from .services.errors import QuizError, QuizFormatError
from .services.generation import generate_quiz
from .services.grading import grade_attempt
from .services.parsing import extract_json, validate_questions

PASSWORD = "Str0ng-Pass!2026"
TEMP_MEDIA = tempfile.mkdtemp()


class FakeLLM(BaseLLMClient):
    name = "fake"

    def __init__(self, replies):
        self.model_name = "fake-1"
        self.replies = list(replies)
        self.prompts = []

    def generate(self, prompt, system="", json_mode=False, temperature=0.4):
        self.prompts.append(prompt)
        return self.replies.pop(0)


def questions_json(count, prefix="Q"):
    return json.dumps({"questions": [
        {"question": f"{prefix}{i} ?", "choices": ["A", "B", "C", "D"],
         "correct_index": 1, "explanation": "Parce que.", "difficulty": "easy"}
        for i in range(count)
    ]})


def make_document(owner, title="Cours", status=CourseDocument.Status.READY, chunks=3):
    document = CourseDocument.objects.create(
        owner=owner, title=title, file=SimpleUploadedFile("c.txt", b"x"),
        file_type="txt", file_size=1, status=status,
    )
    for i in range(chunks):
        DocumentChunk.objects.create(
            document=document, chunk_index=i, text=f"Contenu du passage {i}.",
            page_start=i + 1, page_end=i + 1, char_count=20,
        )
    return document


class ParsingTests(SimpleTestCase):
    def test_plain_json(self):
        self.assertEqual(extract_json('{"a": 1}'), {"a": 1})

    def test_fenced_json(self):
        self.assertEqual(extract_json('```json\n{"a": 1}\n```'), {"a": 1})

    def test_json_surrounded_by_text(self):
        self.assertEqual(extract_json('Voici : {"a": 1} Bonne chance'), {"a": 1})

    def test_invalid_json_raises(self):
        with self.assertRaises(QuizFormatError):
            extract_json("pas du json")

    def _one(self, **changes):
        item = {"question": "Q ?", "choices": ["a", "b", "c", "d"],
                "correct_index": 2, "explanation": "Car."}
        item.update(changes)
        return validate_questions({"questions": [item]}, "medium")

    def test_valid_question_is_kept(self):
        result = self._one()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].difficulty, "medium")  # valeur par défaut

    def test_three_choices_rejected(self):
        self.assertEqual(self._one(choices=["a", "b", "c"]), [])

    def test_duplicate_choices_rejected(self):
        self.assertEqual(self._one(choices=["a", "A", "c", "d"]), [])

    def test_out_of_range_index_rejected(self):
        self.assertEqual(self._one(correct_index=4), [])
        self.assertEqual(self._one(correct_index=True), [])

    def test_missing_explanation_rejected(self):
        self.assertEqual(self._one(explanation=""), [])


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class GenerationTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.alice = User.objects.create_user("alice", "alice@example.com", PASSWORD)
        self.document = make_document(self.alice)

    def test_quiz_is_created_with_one_correct_choice_each(self):
        quiz = generate_quiz(self.document, 5, "easy", FakeLLM([questions_json(5)]))
        self.assertEqual(quiz.questions.count(), 5)
        for question in quiz.questions.all():
            self.assertEqual(question.choices.count(), 4)
            self.assertEqual(question.choices.filter(is_correct=True).count(), 1)

    def test_correct_choice_text_is_preserved_after_shuffle(self):
        quiz = generate_quiz(self.document, 1, "easy", FakeLLM([questions_json(1)]))
        good = quiz.questions.first().choices.get(is_correct=True)
        self.assertEqual(good.text, "B")

    def test_seven_questions_use_two_batches(self):
        llm = FakeLLM([questions_json(5, "A"), questions_json(2, "B")])
        quiz = generate_quiz(self.document, 7, "medium", llm)
        self.assertEqual(len(llm.prompts), 2)
        self.assertEqual(quiz.questions.count(), 7)

    def test_retry_after_invalid_json(self):
        llm = FakeLLM(["pas du json", questions_json(3)])
        quiz = generate_quiz(self.document, 3, "easy", llm)
        self.assertEqual(quiz.questions.count(), 3)

    def test_all_invalid_raises(self):
        with self.assertRaises(QuizError):
            generate_quiz(self.document, 3, "easy", FakeLLM(["x", "y"]))
        self.assertEqual(Quiz.objects.count(), 0)

    def test_prompt_contains_course_text_with_pages(self):
        llm = FakeLLM([questions_json(2)])
        generate_quiz(self.document, 2, "easy", llm)
        self.assertIn("Contenu du passage 0", llm.prompts[0])
        self.assertIn("Pages 1-1", llm.prompts[0])

    def test_document_without_chunks_raises(self):
        empty = make_document(self.alice, chunks=0)
        with self.assertRaises(QuizError):
            generate_quiz(empty, 3, "easy", FakeLLM([]))

    def test_invalid_difficulty_and_count(self):
        with self.assertRaises(QuizError):
            generate_quiz(self.document, 3, "impossible", FakeLLM([]))
        with self.assertRaises(QuizError):
            generate_quiz(self.document, 0, "easy", FakeLLM([]))
        with self.assertRaises(QuizError):
            generate_quiz(self.document, 99, "easy", FakeLLM([]))


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class GradingTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", "alice@example.com", PASSWORD)
        self.document = make_document(self.alice)
        self.quiz = generate_quiz(self.document, 3, "easy", FakeLLM([questions_json(3)]))
        self.questions = list(self.quiz.questions.all())

    def _good(self, question):
        return question.choices.get(is_correct=True).id

    def _bad(self, question):
        return question.choices.filter(is_correct=False).first().id

    def test_all_correct(self):
        attempt = grade_attempt(self.quiz, {q.id: self._good(q) for q in self.questions})
        self.assertEqual((attempt.score, attempt.total), (3, 3))
        self.assertEqual(attempt.grade_out_of_20, 20)

    def test_one_correct_two_wrong(self):
        selections = {self.questions[0].id: self._good(self.questions[0]),
                      self.questions[1].id: self._bad(self.questions[1]),
                      self.questions[2].id: self._bad(self.questions[2])}
        attempt = grade_attempt(self.quiz, selections)
        self.assertEqual(attempt.score, 1)
        self.assertEqual(attempt.grade_out_of_20, 6.7)

    def test_unanswered_counts_as_wrong(self):
        attempt = grade_attempt(self.quiz, {})
        self.assertEqual(attempt.score, 0)
        self.assertEqual(attempt.answers.count(), 3)
        self.assertTrue(all(a.selected_choice is None for a in attempt.answers.all()))

    def test_choice_of_another_question_is_ignored(self):
        foreign = self._good(self.questions[1])
        attempt = grade_attempt(self.quiz, {self.questions[0].id: foreign})
        self.assertEqual(attempt.score, 0)


@override_settings(MEDIA_ROOT=TEMP_MEDIA, LLM_PROVIDER="")
class QuizViewTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", "alice@example.com", PASSWORD)
        self.bob = User.objects.create_user("bob", "bob@example.com", PASSWORD)
        self.client.login(username="alice", password=PASSWORD)
        self.alice_doc = make_document(self.alice, "Cours Alice")
        self.bob_doc = make_document(self.bob, "Cours Bob")

    def _quiz(self, document):
        return generate_quiz(document, 2, "easy", FakeLLM([questions_json(2)]))

    def test_pages_require_login(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("quizzes:list")).status_code, 302)

    def test_list_shows_only_own_quizzes(self):
        self._quiz(self.alice_doc)
        self._quiz(self.bob_doc)
        response = self.client.get(reverse("quizzes:list"))
        self.assertContains(response, "Cours Alice")
        self.assertNotContains(response, "Cours Bob")

    def test_cannot_open_or_take_other_users_quiz(self):
        quiz = self._quiz(self.bob_doc)
        self.assertEqual(self.client.get(reverse("quizzes:detail", args=[quiz.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("quizzes:take", args=[quiz.pk])).status_code, 404)

    def test_cannot_delete_other_users_quiz(self):
        quiz = self._quiz(self.bob_doc)
        response = self.client.post(reverse("quizzes:delete", args=[quiz.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Quiz.objects.filter(pk=quiz.pk).exists())

    def test_delete_requires_post(self):
        quiz = self._quiz(self.alice_doc)
        self.assertEqual(self.client.get(reverse("quizzes:delete", args=[quiz.pk])).status_code, 405)

    def test_create_form_lists_only_own_ready_documents(self):
        make_document(self.alice, "Pas prêt", status=CourseDocument.Status.FAILED)
        response = self.client.get(reverse("quizzes:create"))
        self.assertContains(response, "Cours Alice")
        self.assertNotContains(response, "Cours Bob")
        self.assertNotContains(response, "Pas prêt")

    def test_create_with_fake_llm(self):
        llm = FakeLLM([questions_json(3)])
        with patch("quizzes.services.generation.get_llm_client", return_value=llm):
            response = self.client.post(reverse("quizzes:create"), {
                "document": self.alice_doc.pk, "count": 3, "difficulty": "easy"})
        quiz = Quiz.objects.get()
        self.assertRedirects(response, reverse("quizzes:detail", args=[quiz.pk]))

    def test_cannot_create_quiz_on_other_users_document(self):
        response = self.client.post(reverse("quizzes:create"), {
            "document": self.bob_doc.pk, "count": 3, "difficulty": "easy"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Quiz.objects.count(), 0)

    def test_missing_llm_configuration_shows_error_without_crash(self):
        response = self.client.post(reverse("quizzes:create"), {
            "document": self.alice_doc.pk, "count": 3, "difficulty": "easy"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "LLM")
        self.assertEqual(Quiz.objects.count(), 0)

    def test_take_and_result(self):
        quiz = self._quiz(self.alice_doc)
        data = {f"question_{q.id}": q.choices.get(is_correct=True).id for q in quiz.questions.all()}
        response = self.client.post(reverse("quizzes:take", args=[quiz.pk]), data)
        attempt = QuizAttempt.objects.get()
        self.assertRedirects(response, reverse("quizzes:result", args=[attempt.pk]))
        self.assertEqual(attempt.score, 2)
        self.assertContains(self.client.get(reverse("quizzes:result", args=[attempt.pk])), "Explication")

    def test_cannot_see_other_users_result(self):
        quiz = self._quiz(self.bob_doc)
        attempt = grade_attempt(quiz, {})
        self.assertEqual(self.client.get(reverse("quizzes:result", args=[attempt.pk])).status_code, 404)

    def test_deleting_document_deletes_quizzes(self):
        self._quiz(self.alice_doc)
        self.alice_doc.delete()
        self.assertEqual(Quiz.objects.count(), 0)
        self.assertEqual(Choice.objects.count(), 0)
    from llm import LLMError, get_llm_client


class LLMConfigTests(SimpleTestCase):
    @override_settings(LLM_PROVIDER="ollama", LLM_API_KEY="", LLM_MODEL="qwen3:8b",
                       LLM_TIMEOUT=10, LLM_BASE_URL="")
    def test_ollama_needs_no_api_key(self):
        client = get_llm_client()
        self.assertEqual(client.name, "ollama")
        self.assertEqual(client.base_url, "http://localhost:11434")

    @override_settings(LLM_PROVIDER="gemini", LLM_API_KEY="", LLM_MODEL="x", LLM_TIMEOUT=10)
    def test_gemini_still_needs_api_key(self):
        with self.assertRaises(LLMError):
            get_llm_client()
    
    
    
    
   


class OllamaCleaningTests(SimpleTestCase):
    def test_complete_think_block_is_removed(self):
        self.assertEqual(_strip_reasoning("<think>blabla</think>Réponse."), "Réponse.")

    def test_reasoning_without_opening_tag_is_removed(self):
        self.assertEqual(_strip_reasoning("Je réfléchis...\n</think>\n\nRéponse."), "Réponse.")

    def test_plain_answer_is_unchanged(self):
        self.assertEqual(_strip_reasoning("Réponse."), "Réponse.")