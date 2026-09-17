import io
import json
import os

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from unittest.mock import patch

from consumer.models import Feedback
from services.analytics import affinity, opportunities, overview
from services.formula_lab import build_formula_brief
from services.ai_client import AIUnavailable, analyze_photo
from services.dataset_insights import dataset_insights, public_swatches_near
from services.recommendation import recommend


@patch.dict(os.environ, {"AI_API_KEY": ""})
class DemoFlowTests(TestCase):
    def test_demo_profile_recommendation_feedback_reaches_rd(self):
        self.client.post(reverse("consumer:profile_start"), {
            "nickname": "Ani", "age_range": "25_34", "region": "West Java",
        })
        self.client.post(reverse("consumer:consent"), {"choice": "manual"})
        self.client.post(reverse("consumer:preferences"), {"color": "terracotta", "finish": "satin"})
        response = self.client.post(reverse("consumer:scan"), {"action": "demo"})
        self.assertRedirects(response, reverse("consumer:profile_result"))
        response = self.client.post(reverse("consumer:profile_result"), {
            "skin_tone": "medium", "undertone": "warm", "lip_pigmentation": "medium_high",
            "visible_lip_condition": "Sedikit kering",
        })
        self.assertRedirects(response, reverse("consumer:recommendations"))
        picks = recommend(self.client.session["lip_profile"], self.client.session["preference"])
        self.assertEqual(len(picks), 3)
        self.assertNotIn("SHD009", {pick["shade_id"] for pick in picks})
        recommendation_page = self.client.get(reverse("consumer:recommendations"))
        self.assertContains(recommendation_page, "Coba shade lipstik di fotomu")
        self.assertContains(recommendation_page, "swatch publik")
        shade_id = picks[0]["shade_id"]
        response = self.client.post(reverse("consumer:feedback", args=[shade_id]), {
            "feedback_type": "color_interest", "color_response": "like_it", "comment": "Suka warnanya",
            "rd_consent": "on",
        })
        self.assertRedirects(response, reverse("consumer:feedback_success"))
        self.assertEqual(Feedback.objects.count(), 1)
        self.assertEqual(Feedback.objects.first().rating, None)
        self.assertContains(self.client.get(reverse("research:overview")), "Feedback lokal baru")
        self.assertContains(self.client.get(reverse("research:evidence")), "Suka warnanya")

    def test_wear_feedback_requires_actual_try(self):
        url = reverse("consumer:feedback", args=["SHD001"])
        response = self.client.post(url, {
            "feedback_type": "wear_feedback", "color_response": "just_right", "rating": 5,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Feedback.objects.count(), 0)

        response = self.client.post(url, {
            "feedback_type": "wear_feedback", "color_response": "just_right",
            "texture_response": "comfortable", "finish_response": "just_right",
            "rating": 5, "tried_product": "on", "rd_consent": "on",
        })
        self.assertRedirects(response, reverse("consumer:feedback_success"))
        self.assertEqual(Feedback.objects.first().rating, 5)

    def test_opportunity_shade_cannot_receive_product_feedback(self):
        response = self.client.get(reverse("consumer:feedback", args=["SHD009"]))
        self.assertEqual(response.status_code, 404)

    def test_all_pages_render(self):
        pages = [
            reverse("consumer:home"), reverse("consumer:profile_start"),
            reverse("consumer:consent"), reverse("consumer:preferences"),
            reverse("consumer:scan"), reverse("consumer:profile_result"),
            reverse("consumer:how_it_works"), reverse("research:overview"),
            reverse("research:unmet_demand"), reverse("research:evidence"),
            reverse("research:formula_lab"),
        ]
        for url in pages:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_feedback_request_updates_opportunity_and_formula_brief(self):
        before = next(row for row in opportunities() if row["opportunity_id"] == "OPP001")
        self.client.post(reverse("consumer:feedback", args=["SHD010"]), {
            "feedback_type": "wear_feedback", "color_response": "too_pale",
            "texture_response": "too_sticky", "finish_response": "just_right",
            "rating": 2, "tried_product": "on",
            "desired_color_family": "terracotta", "desired_finish": "satin",
            "comment": "Mau terracotta yang lebih kuat dan tidak lengket",
            "rd_consent": "on",
        })
        after = next(row for row in opportunities() if row["opportunity_id"] == "OPP001")
        self.assertEqual(after["local_requests"], before["local_requests"] + 1)
        self.assertEqual(after["related_issues"], before["related_issues"] + 1)
        self.assertEqual(overview()["local_feedback_count"], 1)
        self.assertContains(self.client.get(reverse("research:unmet_demand")), "1</strong><small>permintaan baru")
        response = self.client.post(reverse("research:formula_lab"), {"opportunity": "OPP001"})
        self.assertContains(response, "Keluhan paling sering")
        self.assertEqual(build_formula_brief("OPP001")["brief"]["opportunity"]["local_requests"], 1)
        self.assertIsNone(build_formula_brief("OPP002")["brief"]["illustrative_composition"])

    def test_interest_affinity_is_count_not_claimed_accuracy(self):
        before = affinity("SHD001", {"skin_tone": "medium", "undertone": "warm"})
        Feedback.objects.create(
            shade_id="SHD001", shade_name="Soft Warm Nude", feedback_type=Feedback.INTEREST,
            skin_tone="medium", undertone="warm", color_response="like_it",
        )
        after = affinity("SHD001", {"skin_tone": "medium", "undertone": "warm"})
        self.assertEqual(after["positive"], before["positive"] + 1)
        self.assertEqual(after["sample"], before["sample"] + 1)

    def test_rd_ai_buttons_have_fallback_and_render_generated_note(self):
        summary_url = reverse("research:unmet_demand")
        fallback = self.client.post(summary_url, {"opportunity": "OPP001"})
        self.assertContains(fallback, "Ringkasan aturan")
        with patch("research.views.generate_opportunity_summary", return_value="Ringkasan AI teruji."):
            response = self.client.post(summary_url, {"opportunity": "OPP001"})
        self.assertContains(response, "Ringkasan AI teruji.")
        with patch("research.views.generate_formula_rationale", return_value="Rasional formula teruji."):
            response = self.client.post(reverse("research:formula_lab"), {"opportunity": "OPP001"})
        self.assertContains(response, "Rasional formula teruji.")

    def test_photo_upload_requires_consent(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        response = self.client.post(reverse("consumer:scan"), {
            "action": "analyze",
            "photo": SimpleUploadedFile("face.png", b"\x89PNG\r\n\x1a\n", content_type="image/png"),
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("lip_profile", self.client.session)

    def test_feedback_requires_rd_consent(self):
        response = self.client.post(reverse("consumer:feedback", args=["SHD001"]), {
            "feedback_type": "color_interest", "color_response": "like_it",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Saya setuju feedback")
        self.assertEqual(Feedback.objects.count(), 0)

    def test_photo_with_consent_uses_vision_result(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.post(reverse("consumer:consent"), {"choice": "photo"})
        with patch("consumer.views.analyze_photo", return_value={
            "skin_tone": "tan", "undertone": "olive",
            "lip_pigmentation": "high", "visible_lip_condition": "two-toned",
            "confidence": "medium",
            "lip_points": {"left": [0.4, 0.6], "top": [0.5, 0.58],
                           "right": [0.6, 0.6], "bottom": [0.5, 0.65]},
        }) as vision:
            response = self.client.post(reverse("consumer:scan"), {
                "action": "analyze",
                "photo": SimpleUploadedFile("face.png", b"\x89PNG\r\n\x1a\nexample", content_type="image/png"),
            })
        self.assertRedirects(response, reverse("consumer:profile_result"))
        self.assertEqual(self.client.session["lip_profile"]["undertone"], "olive")
        self.assertTrue(self.client.session["photo_scanned"])
        vision.assert_called_once()
        self.client.post(reverse("consumer:profile_result"), {
            "skin_tone": "tan", "undertone": "olive", "lip_pigmentation": "high",
        })
        self.assertEqual(self.client.session["lip_profile"]["lip_points"]["top"], [0.5, 0.58])
        self.assertContains(self.client.get(reverse("consumer:recommendations")), "lip-points-data")

    def test_camera_ui_requires_photo_consent_and_jpeg_uses_same_scan(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        scan_url = reverse("consumer:scan")
        self.assertNotContains(self.client.get(scan_url), "Buka kamera")
        self.client.post(reverse("consumer:consent"), {"choice": "photo"})
        page = self.client.get(scan_url)
        self.assertContains(page, "Buka kamera")
        self.assertContains(page, "js/camera.js")
        with patch("consumer.views.analyze_photo", return_value={
            "skin_tone": "medium", "undertone": "warm",
            "lip_pigmentation": "medium", "visible_lip_condition": "",
            "confidence": "low",
        }) as vision:
            response = self.client.post(scan_url, {
                "action": "analyze",
                "photo": SimpleUploadedFile(
                    "foto-kamera.jpg", b"\xff\xd8\xffcamera-test", content_type="image/jpeg"
                ),
            })
        self.assertRedirects(response, reverse("consumer:profile_result"))
        self.assertEqual(vision.call_args.args[1], "image/jpeg")


class AIAdapterTests(SimpleTestCase):
    def test_vision_adapter_parses_structured_response(self):
        result = {"skin_tone": "medium", "undertone": "warm", "lip_pigmentation": "high",
                  "visible_lip_condition": "two-toned", "confidence": "medium",
                  "lip_points": {"left": [0.4, 0.6], "top": [0.5, 0.58],
                                 "right": [0.6, 0.6], "bottom": [0.5, 0.65]}}
        response = {"choices": [{"message": {"content": json.dumps(result)}}]}
        with patch.dict(os.environ, {
            "AI_API_KEY": "test-key", "AI_VISION_MODEL": "vision-test",
            "AI_BASE_URL": "https://example.test/v1",
        }), patch("services.ai_client.urlopen", return_value=io.BytesIO(json.dumps(response).encode())) as send:
            parsed = analyze_photo(b"\x89PNG\r\n\x1a\nexample", "image/png")
        self.assertEqual(parsed["undertone"], "warm")
        self.assertEqual(parsed["lip_points"]["left"], [0.4, 0.6])
        payload = json.loads(send.call_args.args[0].data)
        self.assertEqual(payload["model"], "vision-test")
        self.assertTrue(payload["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_vision_adapter_rejects_unexpected_attributes(self):
        response = {"choices": [{"message": {"content": json.dumps({
            "skin_tone": "unknown", "undertone": "warm", "lip_pigmentation": "high",
        })}}]}
        with patch.dict(os.environ, {
            "AI_API_KEY": "test-key", "AI_VISION_MODEL": "vision-test",
            "AI_BASE_URL": "https://example.test/v1",
        }), patch("services.ai_client.urlopen", return_value=io.BytesIO(json.dumps(response).encode())):
            with self.assertRaises(AIUnavailable):
                analyze_photo(b"image", "image/png")

    def test_vision_adapter_accepts_uncertain_tone(self):
        response = {"choices": [{"message": {"content": json.dumps({
            "skin_tone": "uncertain", "undertone": "uncertain",
            "lip_pigmentation": "uncertain", "visible_lip_condition": "uncertain",
        })}}]}
        with patch.dict(os.environ, {
            "AI_API_KEY": "test-key", "AI_VISION_MODEL": "vision-test",
            "AI_BASE_URL": "https://example.test/v1",
        }), patch("services.ai_client.urlopen", return_value=io.BytesIO(json.dumps(response).encode())):
            self.assertEqual(analyze_photo(b"image", "image/png")["skin_tone"], "uncertain")

    def test_vision_adapter_discards_implausible_lip_points(self):
        response = {"choices": [{"message": {"content": json.dumps({
            "skin_tone": "medium", "undertone": "neutral",
            "lip_pigmentation": "medium", "visible_lip_condition": "",
            "lip_points": {"left": [0.4, 0.6], "top": [0.5, 0.4],
                           "right": [0.6, 0.6], "bottom": [0.5, 0.7]},
        })}}]}
        with patch.dict(os.environ, {
            "AI_API_KEY": "test-key", "AI_VISION_MODEL": "vision-test",
            "AI_BASE_URL": "https://example.test/v1",
        }), patch("services.ai_client.urlopen", return_value=io.BytesIO(json.dumps(response).encode())):
            self.assertNotIn("lip_points", analyze_photo(b"image", "image/png"))

    def test_check_ai_does_not_print_key(self):
        output = io.StringIO()
        payload = {"data": [{"id": "gpt-4o-mini"}]}
        with patch.dict(os.environ, {
            "AI_API_KEY": "private-test-key", "AI_VISION_MODEL": "gpt-4o-mini",
            "AI_TEXT_MODEL": "gpt-4o-mini", "AI_BASE_URL": "https://example.test/v1",
        }), patch("consumer.management.commands.check_ai.urlopen",
                 return_value=io.BytesIO(json.dumps(payload).encode())):
            call_command("check_ai", stdout=output)
        self.assertIn("AI_VISION_MODEL=gpt-4o-mini ditemukan", output.getvalue())
        self.assertNotIn("private-test-key", output.getvalue())

    def test_check_ai_requires_key(self):
        with patch.dict(os.environ, {"AI_API_KEY": ""}):
            with self.assertRaises(CommandError):
                call_command("check_ai")


class DatasetIntegrationTests(SimpleTestCase):
    def test_source_counts_and_hedonic_track_stay_separate(self):
        insight = dataset_insights()
        self.assertEqual(insight["public_lipstick_count"], 191)
        self.assertEqual(insight["synthetic_hedonic_count"], 5000)
        self.assertEqual(sum(item["count"] for item in insight["hedonic_by_family"]), 5000)
        self.assertEqual(insight["synthetic_formula_output_count"], 200)
        picks = recommend({"skin_tone": "medium", "undertone": "warm"}, {})
        examples = public_swatches_near(picks)
        self.assertEqual(len(examples), 3)
        self.assertTrue(all(row["hex"].startswith("#") for row in examples))
"""Additions for consumer/tests.py.

These are NEW test cases to merge into the existing tests.py you already
have (the one with DemoFlowTests / AIAdapterTests / DatasetIntegrationTests).
They do not replace anything -- append the new test methods into
DemoFlowTests, and add the new ColorScienceTests class alongside
AIAdapterTests. Nothing here requires mediapipe to actually run: the pure
math functions (classify_skin_tone/undertone/lip_pigmentation) are tested
directly with known Lab values, and the view-level fallback chain is tested
by mocking analyze_photo_objective / analyze_photo, the same pattern the
existing tests.py already uses for analyze_photo.

Add this import near the top of tests.py, alongside the existing imports:

    from services.color_science import (
        LandmarkNotFound, classify_skin_tone, classify_undertone,
        classify_lip_pigmentation, srgb_to_lab,
    )
"""

from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from services.color_science import (
    LandmarkNotFound, classify_lip_pigmentation, classify_skin_tone,
    classify_undertone, srgb_to_lab,
)


# --- Append these methods into the existing DemoFlowTests(TestCase) class --

class ObjectivePhotoFallbackTests(TestCase):
    """New test class -- exercises the 3-tier fallback added to consumer/views.scan().

    Tier 1: services.color_science.analyze_photo_objective (deterministic, local)
    Tier 2: services.ai_client.analyze_photo (AI vision, only if tier 1 raises LandmarkNotFound)
    Tier 3: MANUAL_PROFILE (only if both above are unavailable)
    """

    def _post_photo(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.post(reverse("consumer:consent"), {"choice": "photo"})
        return self.client.post(reverse("consumer:scan"), {
            "action": "analyze",
            "photo": SimpleUploadedFile("face.png", b"\x89PNG\r\n\x1a\nexample", content_type="image/png"),
        })

    def test_objective_measurement_used_when_landmarks_found(self):
        measured = {
            "skin_tone": "medium", "undertone": "warm", "lip_pigmentation": "medium",
            "visible_lip_condition": "", "confidence": "measured",
            "lip_points": {"left": [0.4, 0.6], "top": [0.5, 0.58],
                           "right": [0.6, 0.6], "bottom": [0.5, 0.65]},
            "measurement": {"method": "mediapipe_face_mesh+cielab", "monk_skin_tone_index": 5,
                            "monk_skin_tone_distance": 3.2, "skin_lab": (60.0, 12.0, 20.0),
                            "lip_lab": (45.0, 25.0, 10.0)},
        }
        with patch("consumer.views.analyze_photo_objective", return_value=measured) as objective:
            response = self._post_photo()
        self.assertRedirects(response, reverse("consumer:profile_result"))
        self.assertEqual(self.client.session["lip_profile"]["confidence"], "measured")
        self.assertEqual(self.client.session["lip_profile"]["undertone"], "warm")
        objective.assert_called_once()
        page = self.client.get(reverse("consumer:profile_result"))
        self.assertContains(page, "Diukur otomatis dari foto")

    def test_falls_back_to_ai_vision_when_landmarks_not_found(self):
        ai_result = {
            "skin_tone": "tan", "undertone": "olive", "lip_pigmentation": "high",
            "visible_lip_condition": "two-toned", "confidence": "medium",
        }
        with patch("consumer.views.analyze_photo_objective", side_effect=LandmarkNotFound("no face")), \
                patch("consumer.views.analyze_photo", return_value=ai_result) as vision:
            response = self._post_photo()
        self.assertRedirects(response, reverse("consumer:profile_result"))
        self.assertEqual(self.client.session["lip_profile"]["undertone"], "olive")
        vision.assert_called_once()

    def test_falls_back_to_manual_when_both_unavailable(self):
        from services.ai_client import AIUnavailable

        with patch("consumer.views.analyze_photo_objective", side_effect=LandmarkNotFound("no face")), \
                patch("consumer.views.analyze_photo", side_effect=AIUnavailable("no key")):
            response = self._post_photo()
        self.assertRedirects(response, reverse("consumer:profile_result"))
        self.assertEqual(self.client.session["lip_profile"]["confidence"], "manual")


class ColorScienceUnitTests(SimpleTestCase):
    """Pure-function tests -- no mediapipe/image decoding involved, just the
    documented classification math. These are what let you show a judge
    "here is a known input, here is the deterministic output" without
    needing a live camera demo.
    """

    def test_classify_skin_tone_matches_nearest_monk_swatch(self):
        # Monk swatch #6 is "#a07e56" -- feed its own Lab value back in and
        # expect it to match itself with ~0 distance.
        lab = srgb_to_lab(0xA0 / 255, 0x7E / 255, 0x56 / 255)
        label, mst_index, distance = classify_skin_tone(lab)
        self.assertEqual(mst_index, 6)
        self.assertLess(distance, 0.5)
        self.assertEqual(label, "medium")

    def test_classify_undertone_warm_vs_cool(self):
        warm_lab = (60.0, 10.0, 25.0)   # b* well above a*, warm per documented heuristic
        cool_lab = (60.0, 10.0, 3.0)    # low b*, cool per documented heuristic
        self.assertEqual(classify_undertone(warm_lab), "warm")
        self.assertEqual(classify_undertone(cool_lab), "cool")

    def test_classify_lip_pigmentation_is_relative_to_skin(self):
        skin_lab = (65.0, 10.0, 15.0)
        light_lip = (60.0, 20.0, 10.0)   # small contrast -> low
        dark_lip = (30.0, 20.0, 10.0)    # large contrast -> high
        self.assertEqual(classify_lip_pigmentation(skin_lab, light_lip), "low")
        self.assertEqual(classify_lip_pigmentation(skin_lab, dark_lip), "high")
