from django.test import TestCase
from django.urls import reverse

from .models import User

PASSWORD = "Str0ng-Pass!2026"


class RegisterTests(TestCase):
    def test_register_page_loads(self):
        response = self.client.get(reverse("accounts:register"))
        self.assertEqual(response.status_code, 200)

    def test_register_creates_user(self):
        response = self.client.post(reverse("accounts:register"), {
            "username": "hadir",
            "email": "hadir@example.com",
            "first_name": "Hadir",
            "last_name": "Bejaoui",
            "password1": PASSWORD,
            "password2": PASSWORD,
        })
        self.assertRedirects(response, reverse("accounts:login"))
        self.assertTrue(User.objects.filter(username="hadir").exists())

    def test_duplicate_email_is_rejected(self):
        User.objects.create_user("a", "same@example.com", PASSWORD)
        response = self.client.post(reverse("accounts:register"), {
            "username": "b",
            "email": "same@example.com",
            "password1": PASSWORD,
            "password2": PASSWORD,
        })
        self.assertEqual(response.status_code, 200)  # le formulaire est ré-affiché
        self.assertFalse(User.objects.filter(username="b").exists())


class LoginAndAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("hadir", "hadir@example.com", PASSWORD)

    def test_login_works(self):
        response = self.client.post(
            reverse("accounts:login"), {"username": "hadir", "password": PASSWORD}
        )
        self.assertRedirects(response, reverse("dashboard"))

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(
            response, f"{reverse('accounts:login')}?next={reverse('dashboard')}"
        )

    def test_profile_requires_login(self):
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 302)

    def test_profile_update(self):
        self.client.login(username="hadir", password=PASSWORD)
        self.client.post(reverse("accounts:profile"), {
            "first_name": "Hadir",
            "last_name": "B.",
            "email": "nouveau@example.com",
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "nouveau@example.com")

    def test_logout(self):
        self.client.login(username="hadir", password=PASSWORD)
        self.client.post(reverse("accounts:logout"))
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)