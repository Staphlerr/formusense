import io
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from consumer.models import Feedback


class RoleAccessTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.consumer = User.objects.create_user("ani", password="StrongDemoPass123!")
        self.consumer.groups.add(Group.objects.get(name="consumer"))
        self.rd_user = User.objects.create_user("formulator", password="StrongDemoPass123!")
        self.rd_user.groups.add(Group.objects.get(name="rd"))
        self.consumer_pages = [
            reverse("consumer:profile_start"), reverse("consumer:consent"),
            reverse("consumer:preferences"), reverse("consumer:scan"),
            reverse("consumer:profile_result"), reverse("consumer:recommendations"),
            reverse("consumer:feedback", args=["SHD001"]),
            reverse("consumer:feedback_success"),
        ]
        self.rd_pages = [
            reverse("research:overview"), reverse("research:unmet_demand"),
            reverse("research:evidence"), reverse("research:formula_lab"),
        ]

    def test_anonymous_redirects_to_correct_login_on_get_and_post(self):
        for path in self.consumer_pages:
            with self.subTest(path=path):
                for method in (self.client.get, self.client.post):
                    self.assertEqual(method(path).status_code, 302)
                    self.assertTrue(method(path).url.startswith(reverse("accounts:consumer_login")))
        for path in self.rd_pages:
            with self.subTest(path=path):
                for method in (self.client.get, self.client.post):
                    self.assertEqual(method(path).status_code, 302)
                    self.assertTrue(method(path).url.startswith(reverse("accounts:rd_login")))

    def test_roles_cannot_access_each_others_pages_or_actions(self):
        self.client.force_login(self.consumer)
        for path in self.rd_pages:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 403)
                self.assertEqual(self.client.post(path, {"opportunity": "OPP001"}).status_code, 403)
        self.client.force_login(self.rd_user)
        for path in self.consumer_pages:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 403)
                self.assertEqual(self.client.post(path, {}).status_code, 403)
        self.assertEqual(Feedback.objects.count(), 0)

    def test_registration_only_creates_consumer_and_cannot_self_select_rd(self):
        response = self.client.post(reverse("accounts:register"), {
            "username": "new_consumer", "password1": "StrongDemoPass123!",
            "password2": "StrongDemoPass123!", "role": "rd",
        })
        self.assertRedirects(response, reverse("consumer:profile_start"))
        user = get_user_model().objects.get(username="new_consumer")
        self.assertTrue(user.groups.filter(name="consumer").exists())
        self.assertFalse(user.groups.filter(name="rd").exists())
        self.assertEqual(self.client.get(reverse("research:overview")).status_code, 403)

    def test_role_specific_login_and_safe_next(self):
        rd_login = reverse("accounts:rd_login")
        response = self.client.post(rd_login, {"username": "ani", "password": "StrongDemoPass123!"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "tidak memiliki akses")
        self.assertEqual(self.client.get(reverse("research:overview")).status_code, 302)
        response = self.client.post(reverse("accounts:consumer_login"), {
            "username": "formulator", "password": "StrongDemoPass123!",
        })
        self.assertEqual(response.status_code, 200)
        response = self.client.post(rd_login, {
            "username": "formulator", "password": "StrongDemoPass123!",
            "next": "https://evil.example/",
        })
        self.assertRedirects(response, reverse("research:overview"))

    def test_switching_account_clears_consumer_profile(self):
        self.client.force_login(self.consumer)
        session = self.client.session
        session["lip_profile"] = {"skin_tone": "medium"}
        session["basic_profile"] = {"nickname": "Ani"}
        session["photo_ai_consent"] = True
        session.save()
        response = self.client.post(reverse("accounts:rd_login"), {
            "username": "formulator", "password": "StrongDemoPass123!",
        })
        self.assertRedirects(response, reverse("research:overview"))
        self.assertNotIn("lip_profile", self.client.session)
        self.assertNotIn("basic_profile", self.client.session)
        self.assertNotIn("photo_ai_consent", self.client.session)

    def test_logout_requires_post_and_revokes_access(self):
        self.client.force_login(self.rd_user)
        self.assertEqual(self.client.get(reverse("accounts:logout")).status_code, 405)
        self.assertEqual(self.client.get(reverse("research:overview")).status_code, 200)
        self.assertRedirects(self.client.post(reverse("accounts:logout")), reverse("consumer:home"))
        self.assertEqual(self.client.get(reverse("research:overview")).status_code, 302)

    def test_rd_account_is_created_only_by_management_command(self):
        output = io.StringIO()
        with patch("accounts.management.commands.create_rd_user.getpass",
                   side_effect=["StrongDemoPass123!", "StrongDemoPass123!"]):
            call_command("create_rd_user", "new_formulator", stdout=output)
        user = get_user_model().objects.get(username="new_formulator")
        self.assertTrue(user.check_password("StrongDemoPass123!"))
        self.assertTrue(user.groups.filter(name="rd").exists())
        self.assertFalse(user.groups.filter(name="consumer").exists())
        self.assertNotIn("StrongDemoPass123!", output.getvalue())
