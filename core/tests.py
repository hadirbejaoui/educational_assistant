"""Tests de la phase 9 : tableau de bord, isolation, échappement, mise en page, erreurs."""

import os
import re
import shutil
import tempfile

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.views.defaults import server_error

from accounts.models import User
from chatbot.models import ChatMessage, Conversation
from courses.models import CourseDocument
from quizzes.models import Choice, Question, Quiz, QuizAttempt, StudentAnswer
from summaries.models import Summary

from .services.dashboard import average_grade, dashboard_data, user_counts

PASSWORD = "Str0ng-Pass!2026"
TEMP_MEDIA = tempfile.mkdtemp()
XSS = "<script>alert('x')</script>"


def make_document(owner, title="Cours", status=CourseDocument.Status.READY):
    return CourseDocument.objects.create(
        owner=owner, title=title, file=SimpleUploadedFile("c.txt", b"x"),
        file_type="txt", file_size=1, status=status,
    )


def make_quiz(document, title="Quiz", question_text="Question ?"):
    quiz = Quiz.objects.create(document=document, owner=document.owner, title=title, difficulty="medium", provider="fake")
    question = Question.objects.create(
        quiz=quiz, order=1, text=question_text, explanation="Parce que.", difficulty="medium"
    )
    Choice.objects.create(question=question, order=1, text="Bonne", is_correct=True)
    Choice.objects.create(question=question, order=2, text="Mauvaise", is_correct=False)
    return quiz


def make_attempt(quiz, score, total, completed=True):
    return QuizAttempt.objects.create(
        quiz=quiz, user=quiz.owner, score=score, total=total,
        completed_at=timezone.now() if completed else None,
    )


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class DataTestCase(TestCase):
    """Deux utilisateurs avec chacun un cours, un résumé, un quiz, une tentative, une conversation."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.alice = User.objects.create_user("alice", "alice@example.com", PASSWORD)
        self.bob = User.objects.create_user("bob", "bob@example.com", PASSWORD)
        self.doc = make_document(self.alice, "Cours Alice")
        self.bob_doc = make_document(self.bob, "Cours secret de Bob")
        Summary.objects.create(document=self.doc, level="short", content="Résumé A", provider="extractive")
        Summary.objects.create(document=self.bob_doc, level="short", content="Résumé secret B", provider="extractive")
        self.quiz = make_quiz(self.doc, "Quiz Alice")
        self.bob_quiz = make_quiz(self.bob_doc, "Quiz secret de Bob")
        self.attempt = make_attempt(self.quiz, 3, 4)
        self.bob_attempt = make_attempt(self.bob_quiz, 1, 4)
        self.conversation = Conversation.objects.create(document=self.doc, owner=self.doc.owner, title="Conv Alice")
        self.bob_conversation = Conversation.objects.create(document=self.bob_doc, owner=self.bob_doc.owner, title="Conv secrète de Bob")
        self.client.login(username="alice", password=PASSWORD)


class DashboardServiceTests(DataTestCase):
    def test_counts_are_per_user(self):
        self.assertEqual(
            user_counts(self.alice),
            {"documents": 1, "summaries": 1, "quizzes": 1, "conversations": 1},
        )

    def test_average_grade_ignores_unfinished_attempts_and_other_users(self):
        make_attempt(self.quiz, 0, 4, completed=False)
        make_attempt(self.quiz, 4, 4)
        self.assertEqual(average_grade(self.alice), 17.5)  # (15 + 20) / 2
        self.assertEqual(average_grade(self.bob), 5.0)

    def test_average_grade_without_attempts(self):
        carol = User.objects.create_user("carol", "carol@example.com", PASSWORD)
        self.assertIsNone(average_grade(carol))

    def test_recent_lists_are_limited_and_filtered(self):
        for i in range(7):
            make_document(self.alice, f"Doc {i}")
        data = dashboard_data(self.alice, recent=5)
        self.assertEqual(len(data["recent_documents"]), 5)
        self.assertTrue(all(d.owner_id == self.alice.id for d in data["recent_documents"]))
        self.assertEqual([a.pk for a in data["recent_attempts"]], [self.attempt.pk])
        self.assertEqual([c.pk for c in data["recent_conversations"]], [self.conversation.pk])


class DashboardViewTests(DataTestCase):
    def test_dashboard_shows_only_own_data(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cours Alice")
        self.assertContains(response, "Quiz Alice")
        self.assertContains(response, "Conv Alice")
        self.assertContains(response, "15,0/20")
        for secret in ("Bob", "secret"):
            self.assertNotContains(response, secret)

    def test_empty_dashboard_invites_to_upload(self):
        User.objects.create_user("carol", "carol@example.com", PASSWORD)
        self.client.login(username="carol", password=PASSWORD)
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "Importer mon premier cours")


class ProtectedPagesTests(TestCase):
    PAGES = [
        "dashboard", "courses:list", "courses:upload", "summaries:list", "quizzes:list",
        "quizzes:create", "quizzes:history", "chatbot:list", "accounts:profile",
    ]

    def test_every_page_requires_login(self):
        login = reverse("accounts:login")
        for name in self.PAGES:
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith(login))


class IsolationTests(DataTestCase):
    def test_lists_and_history_hide_other_users_data(self):
        for name in ("courses:list", "summaries:list", "quizzes:list", "quizzes:history", "chatbot:list"):
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "secret")

    def test_other_users_objects_give_404(self):
        urls = [
            reverse("courses:detail", args=[self.bob_doc.pk]),
            reverse("summaries:document", args=[self.bob_doc.pk]),
            reverse("quizzes:detail", args=[self.bob_quiz.pk]),
            reverse("quizzes:take", args=[self.bob_quiz.pk]),
            reverse("quizzes:result", args=[self.bob_attempt.pk]),
            reverse("chatbot:detail", args=[self.bob_conversation.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 404)
                self.assertContains(response, "Page introuvable", status_code=404)

    def test_history_lists_own_attempts_with_grade(self):
        response = self.client.get(reverse("quizzes:history"))
        self.assertContains(response, "Quiz Alice")
        self.assertContains(response, "15,0/20")
        self.assertContains(response, reverse("quizzes:result", args=[self.attempt.pk]))


class EscapingTests(DataTestCase):
    """Le HTML venant de l'utilisateur ou du modèle (LLM) est affiché comme du texte."""

    def assertEscaped(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, XSS)
        self.assertContains(response, "&lt;script&gt;")

    def test_document_title(self):
        self.doc.title = XSS
        self.doc.save()
        for url in (reverse("dashboard"), reverse("courses:list"), reverse("courses:detail", args=[self.doc.pk])):
            with self.subTest(url=url):
                self.assertEscaped(url)

    def test_summary_content(self):
        Summary.objects.filter(document=self.doc).update(content=XSS)
        self.assertEscaped(reverse("summaries:document", args=[self.doc.pk]))
        self.assertEscaped(reverse("summaries:list"))

    def test_quiz_question_and_explanation(self):
        quiz = make_quiz(self.doc, "Quiz XSS", question_text=XSS)
        Question.objects.filter(quiz=quiz).update(explanation=XSS)
        attempt = make_attempt(quiz, 0, 1)
        StudentAnswer.objects.create(attempt=attempt, question=quiz.questions.first())
        self.assertEscaped(reverse("quizzes:take", args=[quiz.pk]))
        self.assertEscaped(reverse("quizzes:result", args=[attempt.pk]))

    def test_conversation_title_and_messages(self):
        self.conversation.title = XSS
        self.conversation.save()
        ChatMessage.objects.create(
            conversation=self.conversation, role="assistant", content=XSS,
            sources=[{"n": 1, "page_start": 1, "page_end": 1, "chapter": XSS, "cited": True, "excerpt": XSS}],
        )
        self.assertEscaped(reverse("chatbot:detail", args=[self.conversation.pk]))
        self.assertEscaped(reverse("chatbot:list"))


class PaginationTests(DataTestCase):
    def test_document_list_is_paginated(self):
        for i in range(12):
            make_document(self.alice, f"Doc {i:02d}")  # 13 cours au total
        first = self.client.get(reverse("courses:list"))
        self.assertContains(first, "Page 1 sur 2")
        self.assertEqual(len(first.context["documents"]), 12)
        second = self.client.get(reverse("courses:list"), {"page": 2})
        self.assertEqual(len(second.context["documents"]), 1)

    def test_invalid_page_does_not_crash(self):
        for page in ("abc", "999", "-1"):
            with self.subTest(page=page):
                self.assertEqual(self.client.get(reverse("courses:list"), {"page": page}).status_code, 200)


class LayoutTests(DataTestCase):
    def test_sidebar_marks_the_current_section(self):
        response = self.client.get(reverse("quizzes:list"))
        self.assertContains(response, 'id="sidebar"')
        self.assertContains(response, 'aria-controls="sidebar"')
        self.assertContains(response, 'aria-expanded="false"')
        content = response.content.decode()
        quiz_link = content.index(f'href="{reverse("quizzes:list")}"')
        self.assertIn('aria-current="page"', content[quiz_link:quiz_link + 80])

    def test_language_and_skip_link(self):
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, '<html lang="fr">')
        self.assertContains(response, 'href="#main"')

    def test_login_page_has_no_sidebar(self):
        self.client.logout()
        response = self.client.get(reverse("accounts:login"))
        self.assertNotContains(response, 'id="sidebar"')
        self.assertContains(response, "Connexion")

    def test_no_inline_style_or_script_in_pages(self):
        pages = [
            reverse("dashboard"), reverse("courses:list"), reverse("courses:upload"),
            reverse("courses:detail", args=[self.doc.pk]), reverse("quizzes:take", args=[self.quiz.pk]),
            reverse("chatbot:detail", args=[self.conversation.pk]), reverse("accounts:profile"),
        ]
        for url in pages:
            with self.subTest(url=url):
                content = self.client.get(url).content.decode()
                self.assertNotIn("style=", content)
                self.assertNotIn("<style", content)
                self.assertNotRegex(content, r"<script>(?!alert)")  # seulement des <script src=…>

    def test_document_actions_share_the_button_style(self):
        response = self.client.get(reverse("courses:detail", args=[self.doc.pk]))
        self.assertContains(response, '<button type="submit" class="btn btn-secondary">Retraiter</button>', html=True)
        self.assertContains(response, 'class="btn btn-danger"')
        self.assertContains(response, "Étudier ce cours")

    def test_upload_page_exposes_server_limits_to_javascript(self):
        response = self.client.get(reverse("courses:upload"))
        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        self.assertContains(response, f'data-max-bytes="{max_bytes}"')
        self.assertContains(response, "data-dropzone")
        self.assertContains(response, "js/upload.js")

    def test_upload_is_still_validated_by_the_server(self):
        bad = SimpleUploadedFile("virus.exe", b"MZ...")
        response = self.client.post(reverse("courses:upload"), {"title": "x", "file": bad})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Format non autorisé")
        self.assertFalse(CourseDocument.objects.filter(title="x").exists())

    def test_chat_page_has_timeout_and_tools(self):
        ChatMessage.objects.create(
            conversation=self.conversation, role="assistant", content="Réponse",
            sources=[{"n": 1, "page_start": 2, "page_end": 3, "chapter": "", "cited": True, "excerpt": "extrait"}],
        )
        response = self.client.get(reverse("chatbot:detail", args=[self.conversation.pk]))
        self.assertContains(response, f'data-timeout="{settings.LLM_TIMEOUT + 30}"')
        self.assertContains(response, "<summary>Sources (1)</summary>", html=True)
        self.assertContains(response, "data-copy")
        self.assertContains(response, "pages 2 à 3")

    def test_quiz_pages(self):
        take = self.client.get(reverse("quizzes:take", args=[self.quiz.pk]))
        self.assertContains(take, "data-quiz-form")
        self.assertContains(take, "js/quiz.js")
        StudentAnswer.objects.create(attempt=self.attempt, question=self.quiz.questions.first())
        result = self.client.get(reverse("quizzes:result", args=[self.attempt.pk]))
        self.assertContains(result, "15,0/20")
        self.assertContains(result, "grade-good")
        self.assertContains(result, "Explication")
        self.assertContains(result, "Sans réponse")
        self.assertContains(result, "✔ Bonne réponse")

    def test_loading_indicators_on_ai_actions(self):
        detail = self.client.get(reverse("courses:detail", args=[self.doc.pk])).content.decode()
        self.assertGreaterEqual(detail.count("data-loading="), 3)  # discuter, indexer, retraiter
        summaries = self.client.get(reverse("summaries:document", args=[self.doc.pk]))
        self.assertContains(summaries, "data-loading=", count=3)
        self.assertContains(self.client.get(reverse("quizzes:create")), "data-loading=")


class ErrorPagesTests(TestCase):
    def test_custom_404_for_anonymous_user(self):
        response = self.client.get("/cette-page-n-existe-pas/")
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, "Page introuvable", status_code=404)
        self.assertNotContains(response, 'id="sidebar"', status_code=404)

    def test_custom_404_for_logged_in_user_keeps_the_menu(self):
        User.objects.create_user("alice", "alice@example.com", PASSWORD)
        self.client.login(username="alice", password=PASSWORD)
        response = self.client.get("/cette-page-n-existe-pas/")
        self.assertContains(response, 'id="sidebar"', status_code=404)

    def test_custom_500_renders_without_context(self):
        response = server_error(RequestFactory().get("/"))
        self.assertEqual(response.status_code, 500)
        self.assertIn("Erreur du serveur", response.content.decode())


class DesignSystemTests(DataTestCase):
    """Refonte de l'interface : feuilles de style, cache-busting, composants partagés."""

    CSS_FILES = ["tokens", "base", "layout", "components", "pages"]

    def test_stylesheets_are_loaded_in_order_with_a_version(self):
        content = self.client.get(reverse("dashboard")).content.decode()
        positions = []
        for name in self.CSS_FILES:
            match = re.search(rf'href="/static/css/{name}\.css\?v=\d+"', content)
            self.assertIsNotNone(match, f"{name}.css absent ou sans ?v=")
            positions.append(match.start())
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("style.css", content)
        self.assertRegex(content, r'src="/static/js/main\.js\?v=\d+"')

    def test_asset_version_changes_when_the_file_changes(self):
        from django.contrib.staticfiles import finders
        from core.templatetags.ui import asset
        path = finders.find("css/tokens.css")
        before = asset("css/tokens.css")
        stat = os.stat(path)
        try:
            os.utime(path, (stat.st_atime, stat.st_mtime + 10))
            self.assertNotEqual(asset("css/tokens.css"), before)
        finally:
            os.utime(path, (stat.st_atime, stat.st_mtime))

    def test_every_static_reference_exists(self):
        from django.contrib.staticfiles import finders
        for name in self.CSS_FILES:
            self.assertTrue(finders.find(f"css/{name}.css"))
        for name in ("main", "chat", "quiz", "upload"):
            self.assertTrue(finders.find(f"js/{name}.js"))

    def test_icons_come_from_the_inline_sprite(self):
        content = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn('<svg xmlns="http://www.w3.org/2000/svg" class="icon-sprite"', content)
        for name in re.findall(r'<use href="#icon-([\w-]+)"', content):
            self.assertIn(f'id="icon-{name}"', content)
        for glyph in "⌂▤≡☺⏻☰":
            self.assertNotIn(glyph, content)

    def test_sidebar_user_block_and_skip_link(self):
        self.alice.first_name, self.alice.last_name = "Alice", "Martin"
        self.alice.save()
        content = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn('<span class="avatar" aria-hidden="true">AM</span>', content)
        self.assertIn('class="skip-link" href="#main"', content)
        self.assertIn('class="nav-list"', content)

    def test_one_h1_per_page(self):
        pages = [
            reverse("dashboard"), reverse("courses:list"), reverse("courses:detail", args=[self.doc.pk]),
            reverse("courses:upload"), reverse("summaries:list"), reverse("summaries:document", args=[self.doc.pk]),
            reverse("quizzes:list"), reverse("quizzes:history"), reverse("quizzes:take", args=[self.quiz.pk]),
            reverse("quizzes:detail", args=[self.quiz.pk]), reverse("quizzes:result", args=[self.attempt.pk]),
            reverse("chatbot:list"), reverse("chatbot:detail", args=[self.conversation.pk]),
            reverse("accounts:profile"),
        ]
        for url in pages:
            with self.subTest(url=url):
                content = self.client.get(url).content.decode()
                self.assertEqual(content.count("<h1"), 1)

    def test_page_header_escapes_its_title(self):
        self.doc.title = XSS
        self.doc.save()
        content = self.client.get(reverse("courses:detail", args=[self.doc.pk])).content.decode()
        self.assertIn('<h1 class="page-header__title">&lt;script&gt;', content)
        self.assertIn('class="page-header__back"', content)

    def test_chat_label_is_visually_hidden(self):
        content = self.client.get(reverse("chatbot:detail", args=[self.conversation.pk])).content.decode()
        self.assertIn('<label class="sr-only" for="chat-input">Votre question</label>', content)

    def test_initials_filter(self):
        from core.templatetags.ui import initials
        self.assertEqual(initials(User(username="zoe")), "Z")
        self.assertEqual(initials(User(username="x", first_name="hadir", last_name="bejaoui")), "HB")


class AdminThemeTests(TestCase):
    """L'admin Django reprend le design system de l'application (templates/admin/base_site.html)."""

    def test_login_and_pages_use_the_application_theme(self):
        response = self.client.get(reverse("admin:login"))
        self.assertContains(response, "css/admin.css")
        self.assertContains(response, "css/tokens.css")
        self.assertNotContains(response, "dark_mode.css")  # pas de thème sombre, comme l'application
        User.objects.create_superuser("prof", "prof@example.com", PASSWORD)
        self.client.login(username="prof", password=PASSWORD)
        for url in (reverse("admin:index"), reverse("admin:courses_coursedocument_changelist"),
                    reverse("admin:quizzes_quiz_changelist"), reverse("admin:summaries_summary_changelist")):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Assistant pédagogique")
                self.assertContains(response, "Retour à l'application")
                self.assertNotContains(response, ' style="')  # aucune règle inline (CSP stricte)

    def test_password_change_pages_keep_the_theme_without_theme_toggle(self):
        User.objects.create_superuser("prof", "prof@example.com", PASSWORD)
        self.client.login(username="prof", password=PASSWORD)
        for url in (reverse("admin:password_change"), reverse("admin:password_change_done")):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertContains(response, "css/admin.css")
                self.assertContains(response, "Retour à l'application")
                self.assertContains(response, 'class="admin-logout"')
                self.assertContains(response, 'aria-current="page"')
                self.assertNotContains(response, "theme-toggle")  # le thème sombre est désactivé
