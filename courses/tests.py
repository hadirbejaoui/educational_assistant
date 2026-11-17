import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User

from .models import CourseDocument

PASSWORD = "Str0ng-Pass!2026"
TEMP_MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TEMP_MEDIA)
class DocumentTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.alice = User.objects.create_user("alice", "alice@example.com", PASSWORD)
        self.bob = User.objects.create_user("bob", "bob@example.com", PASSWORD)
        self.client.login(username="alice", password=PASSWORD)

    def _pdf(self, name="cours.pdf"):
        return SimpleUploadedFile(name, b"%PDF-1.4 contenu de test", content_type="application/pdf")

    def _make_doc(self, owner, title="Doc"):
        return CourseDocument.objects.create(
            owner=owner, title=title, file=self._pdf(), file_type="pdf", file_size=10
        )

    def test_pages_require_login(self):
        self.client.logout()
        response = self.client.get(reverse("courses:list"))
        self.assertEqual(response.status_code, 302)

    def test_upload_pdf(self):
        response = self.client.post(
            reverse("courses:upload"), {"title": "Maths", "file": self._pdf()}
        )
        doc = CourseDocument.objects.get(title="Maths")
        self.assertRedirects(response, reverse("courses:detail", args=[doc.pk]))
        self.assertEqual(doc.owner, self.alice)
        self.assertEqual(doc.file_type, "pdf")

    def test_upload_txt_without_title_uses_filename(self):
        txt = SimpleUploadedFile("histoire.txt", b"Bonjour", content_type="text/plain")
        self.client.post(reverse("courses:upload"), {"title": "", "file": txt})
        self.assertTrue(CourseDocument.objects.filter(title="histoire").exists())

    def test_wrong_extension_rejected(self):
        exe = SimpleUploadedFile("virus.exe", b"MZ...", content_type="application/octet-stream")
        response = self.client.post(reverse("courses:upload"), {"title": "x", "file": exe})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CourseDocument.objects.count(), 0)

    def test_fake_pdf_rejected(self):
        fake = SimpleUploadedFile("faux.pdf", b"ceci n'est pas un pdf", content_type="application/pdf")
        self.client.post(reverse("courses:upload"), {"title": "x", "file": fake})
        self.assertEqual(CourseDocument.objects.count(), 0)

    @override_settings(MAX_UPLOAD_SIZE_MB=0)
    def test_too_large_rejected(self):
        self.client.post(reverse("courses:upload"), {"title": "x", "file": self._pdf()})
        self.assertEqual(CourseDocument.objects.count(), 0)

    def test_list_shows_only_own_documents(self):
        self._make_doc(self.alice, "Cours Alice")
        self._make_doc(self.bob, "Cours Bob")
        response = self.client.get(reverse("courses:list"))
        self.assertContains(response, "Cours Alice")
        self.assertNotContains(response, "Cours Bob")

    def test_cannot_open_other_users_document(self):
        bob_doc = self._make_doc(self.bob)
        response = self.client.get(reverse("courses:detail", args=[bob_doc.pk]))
        self.assertEqual(response.status_code, 404)

    def test_cannot_delete_other_users_document(self):
        bob_doc = self._make_doc(self.bob)
        response = self.client.post(reverse("courses:delete", args=[bob_doc.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(CourseDocument.objects.filter(pk=bob_doc.pk).exists())

    def test_delete_removes_record_and_file(self):
        doc = self._make_doc(self.alice)
        path = doc.file.path
        self.client.post(reverse("courses:delete", args=[doc.pk]))
        self.assertFalse(CourseDocument.objects.filter(pk=doc.pk).exists())
        import os
        self.assertFalse(os.path.exists(path))