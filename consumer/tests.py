import io
import json
import os

from django.core.management import call_command
from django.core.management.base import CommandError
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from unittest.mock import patch

from consumer.models import Feedback, SavedPhoto, SavedShade
from services.analytics import affinity, opportunities, overview
from services.formula_lab import build_formula_brief
from services.ai_client import AIUnavailable, analyze_photo
from services.dataset_insights import dataset_insights, public_lipstick_stats, public_swatches_near
from services.recommendation import recommend
from services.team_data import (
    build_gap_formula_brief, catalog_shades, gap_candidates,
    same_brand_shades, shade_evidence, shade_feedback_examples, team_dataset_summary,
)
from services.color_science import classify_skin_tone, classify_undertone
from services.local_vision import (
    LocalVisionError, _pigmentation_from_contrast,
    analyze_photo_local, model_available,
)


@patch.dict(os.environ, {"AI_API_KEY": ""})
class DemoFlowTests(TestCase):
    def setUp(self):
        self.consumer = get_user_model().objects.create_user("consumer_test", password="StrongDemoPass123!")
        self.consumer.groups.add(Group.objects.get(name="consumer"))
        self.rd_user = get_user_model().objects.create_user("rd_test", password="StrongDemoPass123!")
        self.rd_user.groups.add(Group.objects.get(name="rd"))
        self.client.force_login(self.consumer)

    def use_rd(self):
        self.client.force_login(self.rd_user)

    def test_demo_profile_recommendation_feedback_reaches_rd(self):
        self.client.post(reverse("consumer:profile_start"), {
            "nickname": "Ani", "age_range": "25_34", "region": "West Java",
        })
        self.client.post(reverse("consumer:consent"), {"choice": "manual"})
        self.client.post(reverse("consumer:preferences"), {"color": "orange", "finish": "matte"})
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
        self.assertContains(recommendation_page, "Kami menemukan")
        self.assertContains(recommendation_page, "Coba warnanya di fotomu")
        self.assertLess(recommendation_page.content.index(b'class="match-grid"'), recommendation_page.content.index(b'id="tryon"'))
        self.assertContains(recommendation_page, "swatch publik")
        shade_id = picks[0]["shade_id"]
        response = self.client.post(reverse("consumer:feedback", args=[shade_id]), {
            "feedback_type": "color_interest", "color_response": "like_it", "comment": "Suka warnanya",
            "rd_consent": "on",
        })
        self.assertRedirects(response, reverse("consumer:feedback_success"))
        self.assertEqual(Feedback.objects.count(), 1)
        self.assertEqual(Feedback.objects.first().rating, None)
        self.use_rd()
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
        consumer_pages = [
            reverse("consumer:home"), reverse("consumer:profile_start"),
            reverse("consumer:consent"), reverse("consumer:preferences"),
            reverse("consumer:scan"), reverse("consumer:profile_result"),
            reverse("consumer:how_it_works"),
        ]
        for url in consumer_pages:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        self.use_rd()
        rd_pages = [
            reverse("research:overview"),
            reverse("research:unmet_demand"), reverse("research:evidence"),
            reverse("research:formula_lab"),
        ]
        for url in rd_pages:
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
        self.use_rd()
        self.assertContains(self.client.get(reverse("research:unmet_demand")), "1</strong><small>permintaan baru")
        response = self.client.post(reverse("research:formula_lab"), {"opportunity": "OPP001"})
        self.assertContains(response, "Keluhan paling sering")
        self.assertEqual(build_formula_brief("OPP001")["brief"]["opportunity"]["local_requests"], 1)
        reference_brief = build_formula_brief("OPP002")["brief"]
        self.assertFalse(reference_brief["needs_reference"])
        self.assertAlmostEqual(sum(reference_brief["baseline_composition"].values()), 100, places=1)

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
        self.use_rd()
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
        self.assertContains(response, "Saya setuju penilaian")
        self.assertEqual(Feedback.objects.count(), 0)

    def test_photo_with_consent_uses_local_vision_result(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.post(reverse("consumer:consent"), {"choice": "photo"})
        with patch("consumer.views.analyze_photo_local", return_value={
            "skin_tone": "tan", "undertone": "olive",
            "lip_pigmentation": "high", "visible_lip_condition": "two-toned",
            "confidence": "medium",
            "lip_points": {"left": [0.4, 0.6], "top": [0.5, 0.58],
                           "right": [0.6, 0.6], "bottom": [0.5, 0.65]},
            "lip_contours": {"outer": [[0.4, 0.6]] * 20, "inner": [[0.5, 0.6]] * 20},
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
        self.assertContains(self.client.get(reverse("consumer:recommendations")), "lip-contours-data")

    def test_camera_ui_requires_photo_consent_and_jpeg_uses_same_scan(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        scan_url = reverse("consumer:scan")
        self.assertNotContains(self.client.get(scan_url), "Buka kamera")
        self.client.post(reverse("consumer:consent"), {"choice": "photo"})
        page = self.client.get(scan_url)
        self.assertContains(page, "Buka kamera")
        self.assertContains(page, "js/camera.js")
        self.assertContains(page, "Mengenali profil bibirmu")
        with patch("consumer.views.analyze_photo_local", return_value={
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

    def test_local_vision_failure_keeps_manual_profile(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.post(reverse("consumer:consent"), {"choice": "photo"})
        with patch("consumer.views.analyze_photo_local", side_effect=LocalVisionError("Wajah tidak terdeteksi.")):
            response = self.client.post(reverse("consumer:scan"), {
                "action": "analyze",
                "photo": SimpleUploadedFile("foto.jpg", b"\xff\xd8\xffexample", content_type="image/jpeg"),
            })
        self.assertRedirects(response, reverse("consumer:profile_result"))
        self.assertEqual(self.client.session["lip_profile"]["confidence"], "manual")
        self.assertTrue(self.client.session["photo_scanned"])

    def test_local_only_photo_consent_does_not_call_external_vision(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.post(reverse("consumer:consent"), {"choice": "photo_local"})
        with patch("consumer.views.analyze_photo_local", side_effect=LocalVisionError("Wajah tidak terdeteksi.")), \
                patch("consumer.views._ai_vision_available", return_value=True), \
                patch("consumer.views.analyze_photo") as external_vision:
            self.client.post(reverse("consumer:scan"), {
                "action": "analyze",
                "photo": SimpleUploadedFile("face.jpg", b"\xff\xd8\xffexample", content_type="image/jpeg"),
            })
        external_vision.assert_not_called()
        self.assertEqual(self.client.session["lip_profile"]["confidence"], "manual")

    def test_explicit_external_photo_consent_enables_ai_fallback(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.post(reverse("consumer:consent"), {"choice": "photo_external"})
        with patch("consumer.views.analyze_photo_local", side_effect=LocalVisionError("Wajah tidak terdeteksi.")), \
                patch("consumer.views._ai_vision_available", return_value=True), \
                patch("consumer.views.analyze_photo", return_value={
                    "skin_tone": "medium", "undertone": "warm", "lip_pigmentation": "medium",
                    "confidence": "medium",
                }) as external_vision:
            self.client.post(reverse("consumer:scan"), {
                "action": "analyze",
                "photo": SimpleUploadedFile("face.jpg", b"\xff\xd8\xffexample", content_type="image/jpeg"),
            })
        external_vision.assert_called_once()
        self.assertEqual(self.client.session["lip_profile"]["undertone"], "warm")


class LocalVisionTests(SimpleTestCase):
    def test_bundled_model_is_available_and_blank_photo_falls_back(self):
        from PIL import Image

        self.assertTrue(model_available())
        image = io.BytesIO()
        Image.new("RGB", (500, 500), (220, 220, 220)).save(image, format="PNG")
        with self.assertRaisesRegex(LocalVisionError, "Wajah tidak terdeteksi"):
            analyze_photo_local(image.getvalue(), "image/png")

    def test_colour_rules_follow_current_provisional_heuristics(self):
        import cv2
        import numpy as np

        skin_lab = cv2.cvtColor(np.asarray([[[215, 189, 150]]], dtype=np.float32) / 255,
                                cv2.COLOR_RGB2LAB)[0, 0]
        self.assertEqual(classify_skin_tone(tuple(float(v) for v in skin_lab))[0], "medium")
        self.assertEqual(_pigmentation_from_contrast(70, 58), "medium_high")
        self.assertEqual(classify_undertone((70, 15, 18)), "neutral")


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
    def test_shade_detail_uses_its_own_demo_feedback_and_swatches(self):
        maple = next(shade for shade in catalog_shades()
                     if shade["shade_name"] == "Maple" and shade["brand"] == "Ronaa.")
        caramel = next(shade for shade in catalog_shades() if shade["shade_name"] == "Caramel")
        profile = {"skin_tone": "medium", "undertone": "warm"}
        maple_feedback = shade_feedback_examples(maple, profile)
        caramel_feedback = shade_feedback_examples(caramel, profile)
        self.assertEqual(len(maple_feedback), 3)
        self.assertTrue(all(item["feedback_id"] in {f"F{number:03d}" for number in range(21, 31)}
                            for item in maple_feedback))
        self.assertFalse({item["feedback_id"] for item in maple_feedback}
                         & {item["feedback_id"] for item in caramel_feedback})
        swatches = public_swatches_near([maple, caramel], per_pick=3)
        self.assertEqual(sum(item["near_demo_shade_id"] == maple["shade_id"] for item in swatches), 3)
        self.assertEqual(sum(item["near_demo_shade_id"] == caramel["shade_id"] for item in swatches), 3)
        self.assertTrue(all(item["brand"] and item["product"] and item["shade"] for item in swatches))
        self.assertEqual(public_lipstick_stats()["swatches"], 191)
        self.assertGreater(public_lipstick_stats()["brands"], 1)
        maple_peers = same_brand_shades(maple)
        self.assertEqual(len(maple_peers), 3)
        self.assertTrue(all(peer["brand"] == maple["brand"]
                            and peer["shade_id"] != maple["shade_id"] for peer in maple_peers))

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

    def test_five_team_datasets_have_the_expected_links_and_formula_total(self):
        summary = team_dataset_summary()
        self.assertEqual((summary["catalog_count"], summary["hedonic_count"],
                          summary["feedback_count"], summary["formula_count"],
                          summary["gap_count"]), (30, 600, 300, 500, 100))
        shade = catalog_shades()[0]
        evidence = shade_evidence(shade, {"skin_tone": "medium", "undertone": "warm"})
        self.assertGreater(evidence["hedonic_sample"], 0)
        self.assertGreater(evidence["review_sample"], 0)
        picks = recommend({"skin_tone": "medium", "undertone": "warm"}, {})
        self.assertEqual(len({pick["shade_id"] for pick in picks}), 3)
        self.assertTrue(all(pick["shade_id"] in {row["shade_id"] for row in catalog_shades()}
                            for pick in picks))
        self.assertEqual(len(gap_candidates()), 100)
        brief = build_gap_formula_brief(0)
        self.assertEqual(brief["total"], 100)
        self.assertEqual(len(brief["references"]), 3)


class TeamDataFlowTests(TestCase):
    def setUp(self):
        self.consumer = get_user_model().objects.create_user("team_consumer", password="StrongDemoPass123!")
        self.consumer.groups.add(Group.objects.get(name="consumer"))
        self.rd_user = get_user_model().objects.create_user("team_rd", password="StrongDemoPass123!")
        self.rd_user.groups.add(Group.objects.get(name="rd"))

    def test_recommendations_show_maple_specific_detail(self):
        self.client.force_login(self.consumer)
        session = self.client.session
        session["lip_profile"] = {"skin_tone": "medium", "undertone": "warm",
                                  "lip_pigmentation": "medium"}
        session["preference"] = {"color": "orange", "finish": "glasting"}
        session.save()
        with patch("consumer.views._ai_text_available", return_value=False), \
                patch("consumer.views.generate_personal_note", return_value="Catatan uji"):
            page = self.client.get(reverse("consumer:recommendations"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Apa kata konsumen tentang Maple")
        maple = next(pick for pick in page.context["picks"] if pick["shade_name"] == "Maple")
        self.assertEqual(len(maple["feedback_examples"]), 3)
        self.assertTrue(all(item["feedback_id"] in {f"F{number:03d}" for number in range(21, 31)}
                            for item in maple["feedback_examples"]))
        self.assertEqual(sum(item["near_demo_shade_id"] == maple["shade_id"]
                             for item in page.context["public_examples"]), 3)
        self.assertEqual(len(maple["brand_peers"]), 3)
        self.assertContains(page, "Shade lain dari Ronaa.")
        self.assertContains(page, "Contoh produk lipstik dari merek publik")
        self.assertNotContains(page, "★ AI")
        maple_index = next(index for index, pick in enumerate(page.context["picks"])
                           if pick["shade_id"] == maple["shade_id"])
        self.assertContains(page, f'data-select-preview="detail-{maple_index}"')
        self.assertContains(page, f'data-open-detail="detail-{maple_index}"')
        self.assertNotContains(page, 'shade-detail-panel is-open')

    def test_catalog_recommendation_feedback_and_rd_formula_flow(self):
        self.client.force_login(self.consumer)
        session = self.client.session
        session["lip_profile"] = {"skin_tone": "medium", "undertone": "warm",
                                  "lip_pigmentation": "medium"}
        session["preference"] = {"finish": "satin"}
        session.save()
        page = self.client.get(reverse("consumer:recommendations"))
        self.assertEqual(len(page.context["picks"]), 3)
        self.assertEqual(page.context["finish_gap"], "satin")
        shade = recommend(session["lip_profile"], session["preference"])[0]
        response = self.client.post(reverse("consumer:feedback", args=[shade["shade_id"]]), {
            "feedback_type": "color_interest", "color_response": "like_it",
            "desired_finish": "satin", "rd_consent": "on",
        })
        self.assertRedirects(response, reverse("consumer:feedback_success"))
        self.assertEqual(Feedback.objects.first().shade_id, shade["shade_id"])

        self.client.force_login(self.rd_user)
        gap_page = self.client.get(reverse("research:unmet_demand"))
        self.assertContains(gap_page, "Unmet Demand")
        self.assertTrue(gap_page.context["opportunities"])
        satin = next(item for item in gap_page.context["finish_coverage"] if item["finish"] == "satin")
        self.assertEqual(satin["catalog_count"], 0)
        self.assertEqual(satin["local_requests"], 1)
        evidence_page = self.client.get(reverse("research:evidence"))
        self.assertContains(evidence_page, "Keluhan pemakaian · internal")
        self.assertGreater(evidence_page.context["team_feedback"]["count"], 0)
        brief_page = self.client.post(reverse("research:formula_lab"), {"gap": "0"})
        self.assertContains(brief_page, "Komposisi awal untuk diuji")
        self.assertEqual(brief_page.context["team_brief"]["total"], 100)
from services.color_science import (
    classify_lip_pigmentation, classify_undertone, srgb_to_lab,
)


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
        warm_lab = (60.0, 10.0, 17.0)   # warm band, below the olive cutoff
        cool_lab = (60.0, 10.0, 3.0)    # low b*, cool per documented heuristic
        self.assertEqual(classify_undertone(warm_lab), "warm")
        self.assertEqual(classify_undertone(cool_lab), "cool")

    def test_classify_lip_pigmentation_is_relative_to_skin(self):
        skin_lab = (65.0, 10.0, 15.0)
        light_lip = (60.0, 20.0, 10.0)   # small contrast -> low
        dark_lip = (30.0, 20.0, 10.0)    # large contrast -> high
        self.assertEqual(classify_lip_pigmentation(skin_lab, light_lip), "low")
        self.assertEqual(classify_lip_pigmentation(skin_lab, dark_lip), "high")


class AccountCollectionTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user("saved_owner", password="StrongDemoPass123!")
        self.other = get_user_model().objects.create_user("saved_other", password="StrongDemoPass123!")
        consumer_group = Group.objects.get(name="consumer")
        self.owner.groups.add(consumer_group)
        self.other.groups.add(consumer_group)
        self.client.force_login(self.owner)

    def test_saved_shade_belongs_to_account_and_can_be_removed(self):
        url = reverse("consumer:save_shade")
        self.assertEqual(self.client.post(url, {"shade_id": "SHD001", "action": "save"}).status_code, 200)
        self.client.post(url, {"shade_id": "SHD001", "action": "save"})
        self.assertEqual(SavedShade.objects.filter(user=self.owner).count(), 1)
        self.assertContains(self.client.get(reverse("consumer:account_profile")), "Soft Warm Nude")
        self.assertEqual(self.client.post(url, {"shade_id": "SHD009", "action": "save"}).status_code, 400)
        self.client.force_login(self.other)
        self.assertNotContains(self.client.get(reverse("consumer:account_profile")), "Soft Warm Nude")
        self.client.force_login(self.owner)
        self.assertRedirects(self.client.post(url, {"shade_id": "SHD001", "action": "remove",
                                                     "from_profile": "1"}), reverse("consumer:account_profile"))
        self.assertFalse(SavedShade.objects.filter(user=self.owner).exists())

    def test_photo_history_is_explicit_private_and_deletable(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        image = io.BytesIO()
        Image.new("RGB", (32, 32), "#b05f49").save(image, format="PNG")
        upload = SimpleUploadedFile("hasil.png", image.getvalue(), content_type="image/png")
        response = self.client.post(reverse("consumer:save_photo"), {
            "shade_id": "SHD001", "photo": upload,
            "nickname": "Maya", "age_range": "25_34", "region": "West Java",
        })
        self.assertEqual(response.status_code, 200)
        entry = SavedPhoto.objects.get(user=self.owner)
        self.assertTrue(entry.image_jpeg.startswith(b"\xff\xd8"))
        self.assertEqual((entry.nickname, entry.age_range, entry.region),
                         ("Maya", "25_34", "West Java"))
        photo_url = reverse("consumer:profile_photo", args=[entry.pk])
        self.assertEqual(self.client.get(photo_url).status_code, 200)
        self.assertContains(self.client.get(reverse("consumer:account_profile")), photo_url)
        self.assertContains(self.client.get(reverse("consumer:account_profile")), "Maya")
        self.assertContains(self.client.get(reverse("consumer:account_profile")), "Jawa Barat")
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(photo_url).status_code, 404)
        self.assertEqual(self.client.post(reverse("consumer:delete_photo", args=[entry.pk])).status_code, 404)
        self.client.force_login(self.owner)
        self.assertRedirects(self.client.post(reverse("consumer:delete_photo", args=[entry.pk])),
                             reverse("consumer:account_profile"))
        self.assertFalse(SavedPhoto.objects.exists())

    def test_photo_labels_are_snapshots_per_photo(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image

        image = io.BytesIO()
        Image.new("RGB", (32, 32), "#b05f49").save(image, format="PNG")
        for shade_id, nickname, age_range, region in [
            ("SHD001", "Maya", "25_34", "West Java"),
            ("SHD002", "Rani", "18_24", "Jakarta"),
        ]:
            upload = SimpleUploadedFile("hasil.png", image.getvalue(), content_type="image/png")
            response = self.client.post(reverse("consumer:save_photo"), {
                "shade_id": shade_id, "photo": upload, "nickname": nickname,
                "age_range": age_range, "region": region,
            })
            self.assertEqual(response.status_code, 200)
        photos = list(SavedPhoto.objects.filter(user=self.owner).order_by("pk"))
        self.assertEqual([(photo.nickname, photo.age_range, photo.region, photo.shade_id)
                          for photo in photos], [
            ("Maya", "25_34", "West Java", "SHD001"),
            ("Rani", "18_24", "Jakarta", "SHD002"),
        ])

    def test_photo_history_rejects_non_image(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        response = self.client.post(reverse("consumer:save_photo"), {
            "shade_id": "SHD001",
            "photo": SimpleUploadedFile("hasil.png", b"not an image", content_type="image/png"),
        })
        self.assertEqual(response.status_code, 400)
        self.assertFalse(SavedPhoto.objects.exists())
