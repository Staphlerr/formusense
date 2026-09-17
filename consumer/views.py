import os
from io import BytesIO

from django.contrib import messages
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from PIL import Image, ImageOps, UnidentifiedImageError

from accounts.access import consumer_required
from consumer.forms import FeedbackForm, LipProfileForm, PreferenceForm, ProfileStartForm
from consumer.models import SavedPhoto, SavedShade
from services.ai_client import AIUnavailable, analyze_photo, generate_personal_note
from services.analytics import affinity
from services.data import shade_by_id
from services.dataset_insights import public_lipstick_stats, public_swatches_near
from services.local_vision import LocalVisionError, analyze_photo_local, model_available
from services.recommendation import personalize, recommend
from services.team_data import catalog_shades, hedonic_spectrum, same_brand_shades, shade_feedback_examples


DEMO_PROFILE = {
    "skin_tone": "medium", "undertone": "warm", "lip_pigmentation": "medium_high",
    "visible_lip_condition": "Sedikit kering; dua warna (contoh simulasi)",
    "confidence": "demo",
}
MANUAL_PROFILE = {
    "skin_tone": "medium", "undertone": "uncertain", "lip_pigmentation": "uncertain",
    "visible_lip_condition": "", "confidence": "manual",
}


def _ai_vision_available() -> bool:
    return bool(os.environ.get("AI_API_KEY") and os.environ.get("AI_VISION_MODEL"))


def _ai_text_available() -> bool:
    return bool(os.environ.get("AI_API_KEY") and os.environ.get("AI_TEXT_MODEL"))


def home(request):
    return render(request, "consumer/home.html")


@consumer_required
def profile_start(request):
    form = ProfileStartForm(request.POST or None, initial=request.session.get("basic_profile"))
    if request.method == "POST" and form.is_valid():
        request.session["basic_profile"] = form.cleaned_data
        return redirect("consumer:consent")
    return render(request, "consumer/profile_start.html", {"form": form})


@consumer_required
def consent(request):
    if request.method == "POST":
        choice = request.POST.get("choice")
        request.session["photo_consent"] = choice in {"photo", "photo_local", "photo_external"}
        request.session["photo_ai_consent"] = choice == "photo_external"
        if not request.session["photo_consent"]:
            request.session["photo_scanned"] = False
        return redirect("consumer:preferences")
    return render(request, "consumer/consent.html")


@consumer_required
def preferences(request):
    form = PreferenceForm(request.POST or None, initial=request.session.get("preference"))
    if request.method == "POST" and form.is_valid():
        request.session["preference"] = form.cleaned_data
        return redirect("consumer:scan")
    return render(request, "consumer/preferences.html", {"form": form})


@consumer_required
def scan(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "demo":
            request.session["lip_profile"] = DEMO_PROFILE.copy()
            request.session["photo_scanned"] = False
            return redirect("consumer:profile_result")
        if action == "manual":
            request.session["lip_profile"] = MANUAL_PROFILE.copy()
            request.session["photo_scanned"] = False
            return redirect("consumer:profile_result")
        photo = request.FILES.get("photo")
        if not request.session.get("photo_consent"):
            messages.error(request, "Analisis foto memerlukan persetujuan terlebih dahulu.")
        elif photo is None:
            messages.error(request, "Pilih foto terlebih dahulu.")
        elif photo.content_type not in {"image/jpeg", "image/png"} or photo.size > 10 * 1024 * 1024:
            messages.error(request, "Gunakan JPG/PNG berukuran maksimal 10 MB.")
        else:
            photo_bytes = photo.read()
            matches_type = (
                                   photo.content_type == "image/jpeg" and photo_bytes.startswith(b"\xff\xd8\xff")
                           ) or (
                                   photo.content_type == "image/png" and photo_bytes.startswith(b"\x89PNG\r\n\x1a\n")
                           )
            if not matches_type:
                messages.error(request, "Isi file tidak sesuai format JPG/PNG.")
                return render(request, "consumer/scan.html", {
                    "photo_consent": True,
                    "local_vision_available": model_available(),
                    "ai_available": _ai_vision_available(),
                    "photo_ai_consent": request.session.get("photo_ai_consent", False),
                })
            request.session["photo_scanned"] = True
            # Three-tier fallback, in order of how grounded/explainable the result is:
            # 1) local deterministic CV + colorimetry (services.local_vision) --
            #    no API call, every number traces back to a measured pixel.
            # 2) AI vision API (services.ai_client) -- only if a face/lips could
            #    not be located/measured reliably by tier 1.
            # 3) manual profile form -- only if both of the above are unavailable.
            try:
                request.session["lip_profile"] = analyze_photo_local(photo_bytes, photo.content_type)
                messages.info(
                    request,
                    "Kontur wajah dan bibir berhasil terdeteksi; warna diukur langsung dari foto "
                    "tanpa AI. Sesuaikan nilainya di bawah bila hasilnya kurang tepat.",
                )
            except LocalVisionError as error:
                if request.session.get("photo_ai_consent") and _ai_vision_available():
                    try:
                        request.session["lip_profile"] = analyze_photo(photo_bytes, photo.content_type)
                        messages.info(
                            request,
                            f"{error} Menggunakan estimasi AI vision sebagai cadangan. "
                            "Sesuaikan nilainya di bawah bila hasilnya kurang tepat.",
                        )
                    except AIUnavailable:
                        request.session["lip_profile"] = MANUAL_PROFILE.copy()
                        messages.warning(request, f"{error} AI cadangan tidak tersedia. Isi profil secara manual.")
                else:
                    request.session["lip_profile"] = MANUAL_PROFILE.copy()
                    messages.warning(
                        request,
                        f"{error} Silakan lengkapi profil secara manual; "
                        "foto yang sudah diambil tetap bisa dipakai untuk mencoba shade.",
                    )
            return redirect("consumer:profile_result")
    return render(request, "consumer/scan.html", {
        "photo_consent": request.session.get("photo_consent", False),
        "local_vision_available": model_available(),
        "ai_available": _ai_vision_available(),
        "photo_ai_consent": request.session.get("photo_ai_consent", False),
    })


@consumer_required
def profile_result(request):
    current = request.session.get("lip_profile", MANUAL_PROFILE)
    form = LipProfileForm(request.POST or None, initial=current)
    if request.method == "POST" and form.is_valid():
        request.session["lip_profile"] = {**current, **form.cleaned_data, "confidence": "user_reviewed"}
        return redirect("consumer:recommendations")
    source_labels = {
        "demo": "Profil contoh",
        "manual": "Input manual",
        "local_low": "Kontur lokal · isi warna manual",
        "local_estimate": "Diukur lokal dari foto (deteksi wajah + analisis warna, bukan AI)",
        "low": "Perkiraan AI vision · periksa kembali",
        "medium": "Perkiraan AI vision · periksa kembali",
        "high": "Perkiraan AI vision · periksa kembali",
        "user_reviewed": "Sudah diperiksa pengguna",
    }
    return render(request, "consumer/profile_result.html", {
        "form": form,
        "source_label": source_labels.get(current.get("confidence"), "Perkiraan awal"),
        "analysis_note": current.get("analysis_note", ""),
        # Raw Lab/measurement numbers when tier 1 (local_vision) produced
        # them -- absent for demo/manual/AI-vision profiles, template should
        # only render this block when it's present.
        "measurement": current.get("measurement"),
    })


@consumer_required
def account_profile(request):
    saved_shades = []
    for entry in SavedShade.objects.filter(user=request.user):
        shade = shade_by_id(entry.shade_id, available_only=True)
        if shade:
            saved_shades.append({"entry": entry, "shade": shade})
    return render(request, "consumer/account_profile.html", {
        "saved_shades": saved_shades,
        "saved_photos": SavedPhoto.objects.filter(user=request.user).defer("image_jpeg")[:8],
        "photo_limit": 8,
        "display_name": request.session.get("basic_profile", {}).get("nickname") or request.user.username,
        "color_profile": request.session.get("lip_profile"),
    })


@consumer_required
@require_POST
def save_shade(request):
    shade_id = request.POST.get("shade_id", "")
    shade = shade_by_id(shade_id, available_only=True)
    if shade is None:
        return JsonResponse({"error": "Shade tidak tersedia."}, status=400)
    action = request.POST.get("action")
    if action == "save":
        SavedShade.objects.get_or_create(user=request.user, shade_id=shade_id)
    elif action == "remove":
        SavedShade.objects.filter(user=request.user, shade_id=shade_id).delete()
    else:
        return JsonResponse({"error": "Pilihan tidak dikenal."}, status=400)
    if request.POST.get("from_profile") == "1":
        return redirect("consumer:account_profile")
    return JsonResponse({"saved": action == "save"})


@consumer_required
@require_POST
def save_photo(request):
    shade_id = request.POST.get("shade_id", "")
    shade = shade_by_id(shade_id, available_only=True)
    photo = request.FILES.get("photo")
    if shade is None or photo is None:
        return JsonResponse({"error": "Pilih shade dan foto hasil terlebih dahulu."}, status=400)
    if photo.content_type not in {"image/jpeg", "image/png"} or photo.size > 3 * 1024 * 1024:
        return JsonResponse({"error": "Gunakan foto JPG/PNG maksimal 3 MB."}, status=400)
    if SavedPhoto.objects.filter(user=request.user).count() >= 8:
        return JsonResponse({"error": "Riwayat penuh. Hapus satu foto sebelum menyimpan lagi."}, status=400)
    try:
        image = Image.open(photo)
        if image.format not in {"JPEG", "PNG"} or max(image.size) > 4096:
            raise ValueError("Format atau ukuran gambar tidak sesuai")
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((960, 960))
        output = BytesIO()
        image.save(output, format="JPEG", quality=78, optimize=True)
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        return JsonResponse({"error": "Foto tidak dapat dibaca."}, status=400)
    entry = SavedPhoto.objects.create(
        user=request.user, shade_id=shade_id, shade_name=shade["shade_name"],
        image_jpeg=output.getvalue(),
    )
    return JsonResponse({"saved": True, "photo_id": entry.pk,
                         "profile_url": reverse("consumer:account_profile")})


@consumer_required
def profile_photo(request, photo_id):
    photo = get_object_or_404(SavedPhoto, pk=photo_id, user=request.user)
    response = HttpResponse(photo.image_jpeg, content_type="image/jpeg")
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@consumer_required
@require_POST
def delete_photo(request, photo_id):
    photo = get_object_or_404(SavedPhoto, pk=photo_id, user=request.user)
    photo.delete()
    messages.success(request, "Foto dihapus dari riwayat akun.")
    return redirect("consumer:account_profile")


@consumer_required
def recommendations(request):
    profile = request.session.get("lip_profile")
    if not profile:
        return redirect("consumer:profile_result")
    preference = request.session.get("preference", {})
    picks = recommend(profile, preference)
    # Optional, bounded AI personalization layer -- see
    # services.recommendation.personalize()'s docstring: it can only choose
    # among the candidates recommend() already scored deterministically,
    # never invent a shade. Skipped entirely (falls back to the
    # deterministic picks untouched) when AI_TEXT_MODEL isn't configured,
    # or silently on any per-role failure. This adds up to 3 sequential AI
    # calls (~12s timeout each) -- if a live demo needs to stay snappy,
    # comment this block out and recommend()'s output is already complete.
    if _ai_text_available():
        picks = personalize(picks, profile, preference)
    for pick in picks:
        pick["affinity"] = affinity(pick["shade_id"], profile)
        pick["feedback_examples"] = shade_feedback_examples(pick, profile)
        pick["brand_peers"] = same_brand_shades(pick)
    note = picks[1]["reason"]
    note_source = "Aturan katalog"
    note_key = f"{picks[1]['shade_id']}:{profile.get('skin_tone')}:{profile.get('undertone')}:{profile.get('lip_pigmentation')}"
    cached_note = request.session.get("personal_note_cache", {})
    if cached_note.get("key") == note_key:
        note = cached_note["text"]
        note_source = "AI text · berdasarkan profil dan katalog"
    else:
        try:
            note = generate_personal_note(profile, picks[1])
            note_source = "AI text · berdasarkan profil dan katalog"
            request.session["personal_note_cache"] = {"key": note_key, "text": note}
        except AIUnavailable:
            pass
    for index, pick in enumerate(picks):
        pick["display_note"] = note if index == 1 else pick["reason"]
        pick["display_note_source"] = note_source if index == 1 else "Aturan katalog"
    return render(request, "consumer/recommendations.html", {
        "picks": picks, "profile": profile, "personal_note": note,
        "note_source": note_source, "spectrum": hedonic_spectrum(profile),
        "finish_gap": (preference.get("finish")
                       if preference.get("finish")
                          and preference["finish"] not in {row["finish"] for row in catalog_shades()}
                       else None),
        "public_examples": public_swatches_near(picks, per_pick=3),
        "public_lipstick_stats": public_lipstick_stats(),
        "photo_scanned": request.session.get("photo_scanned", False),
        "saved_shade_ids": list(SavedShade.objects.filter(user=request.user)
                                .values_list("shade_id", flat=True)),
        # Shape differs by which fallback tier produced the profile:
        # local_vision -> "lip_contours" (outer/inner point arrays),
        # AI vision (services.ai_client.analyze_photo) -> "lip_points" (a
        # 4-point left/right/top/bottom box). Pass both through and let the
        # template render whichever is present -- do not assume only one
        # shape will ever show up here.
        "lip_contours": profile.get("lip_contours") if request.session.get("photo_scanned") else None,
        "lip_points": profile.get("lip_points") if request.session.get("photo_scanned") else None,
    })


@consumer_required
def feedback(request, shade_id):
    shade = shade_by_id(shade_id, available_only=True)
    if shade is None:
        raise Http404("Shade tidak tersedia dalam katalog rekomendasi")
    form = FeedbackForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        entry = form.save(commit=False)
        profile = request.session.get("lip_profile", {})
        basic = request.session.get("basic_profile", {})
        entry.shade_id = shade_id
        entry.shade_name = shade["shade_name"]
        entry.region = basic.get("region", "")
        entry.skin_tone = profile.get("skin_tone", "")
        entry.undertone = profile.get("undertone", "")
        entry.lip_pigmentation = profile.get("lip_pigmentation", "")
        if entry.feedback_type == entry.INTEREST:
            entry.texture_response = ""
            entry.finish_response = ""
            entry.rating = None
        entry.save()
        request.session["last_feedback"] = {
            "shade_name": entry.shade_name,
            "feedback_type": entry.feedback_type,
            "desired_color_family": entry.desired_color_family,
        }
        return redirect("consumer:feedback_success")
    return render(request, "consumer/feedback.html", {"form": form, "shade": shade})


@consumer_required
def feedback_success(request):
    return render(request, "consumer/feedback_success.html", {
        "last_feedback": request.session.get("last_feedback", {}),
    })


def how_it_works(request):
    return render(request, "consumer/how_it_works.html")