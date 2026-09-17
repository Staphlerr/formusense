from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render

from consumer.forms import FeedbackForm, LipProfileForm, PreferenceForm, ProfileStartForm
from services.ai_client import AIUnavailable, generate_personal_note
from services.analytics import affinity, community_spectrum
from services.data import shade_by_id
from services.dataset_insights import public_swatches_near
from services.local_vision import LocalVisionError, analyze_photo_local, model_available
from services.recommendation import recommend


DEMO_PROFILE = {
    "skin_tone": "medium", "undertone": "warm", "lip_pigmentation": "medium_high",
    "visible_lip_condition": "Sedikit kering; dua warna (contoh simulasi)",
    "confidence": "demo",
}
MANUAL_PROFILE = {
    "skin_tone": "medium", "undertone": "uncertain", "lip_pigmentation": "uncertain",
    "visible_lip_condition": "", "confidence": "manual",
}


def home(request):
    return render(request, "consumer/home.html")


def profile_start(request):
    form = ProfileStartForm(request.POST or None, initial=request.session.get("basic_profile"))
    if request.method == "POST" and form.is_valid():
        request.session["basic_profile"] = form.cleaned_data
        return redirect("consumer:consent")
    return render(request, "consumer/profile_start.html", {"form": form})


def consent(request):
    if request.method == "POST":
        request.session["photo_consent"] = request.POST.get("choice") == "photo"
        if not request.session["photo_consent"]:
            request.session["photo_scanned"] = False
        return redirect("consumer:preferences")
    return render(request, "consumer/consent.html")


def preferences(request):
    form = PreferenceForm(request.POST or None, initial=request.session.get("preference"))
    if request.method == "POST" and form.is_valid():
        request.session["preference"] = form.cleaned_data
        return redirect("consumer:scan")
    return render(request, "consumer/preferences.html", {"form": form})


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
                    "photo_consent": True, "local_vision_available": model_available(),
                })
            request.session["photo_scanned"] = True
            try:
                request.session["lip_profile"] = analyze_photo_local(photo_bytes, photo.content_type)
                messages.info(request, "Analisis lokal selesai. Periksa dan koreksi hasil warna jika perlu.")
            except LocalVisionError as error:
                request.session["lip_profile"] = MANUAL_PROFILE.copy()
                messages.warning(request, f"{error} Isi profil secara manual; foto tetap bisa dipakai untuk coba shade.")
            return redirect("consumer:profile_result")
    return render(request, "consumer/scan.html", {
        "photo_consent": request.session.get("photo_consent", False),
        "local_vision_available": model_available(),
    })


def profile_result(request):
    current = request.session.get("lip_profile", MANUAL_PROFILE)
    form = LipProfileForm(request.POST or None, initial=current)
    if request.method == "POST" and form.is_valid():
        request.session["lip_profile"] = {**current, **form.cleaned_data, "confidence": "user_reviewed"}
        return redirect("consumer:recommendations")
    source_labels = {"demo": "Profil contoh", "manual": "Input manual", "local_low": "Kontur lokal · isi warna manual",
                     "local_estimate": "Perkiraan foto lokal · periksa kembali", "low": "Perkiraan AI · periksa kembali",
                     "medium": "Perkiraan AI · periksa kembali", "high": "Perkiraan AI · periksa kembali",
                     "user_reviewed": "Sudah diperiksa pengguna"}
    return render(request, "consumer/profile_result.html", {
        "form": form, "source_label": source_labels.get(current.get("confidence"), "Perkiraan awal"),
        "analysis_note": current.get("analysis_note", ""),
    })


def recommendations(request):
    profile = request.session.get("lip_profile")
    if not profile:
        return redirect("consumer:profile_result")
    picks = recommend(profile, request.session.get("preference", {}))
    for pick in picks:
        pick["affinity"] = affinity(pick["shade_id"], profile)
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
    return render(request, "consumer/recommendations.html", {
        "picks": picks, "profile": profile, "personal_note": note,
        "note_source": note_source, "spectrum": community_spectrum(profile),
        "public_examples": public_swatches_near(picks),
        "photo_scanned": request.session.get("photo_scanned", False),
        "lip_points": profile.get("lip_points") if request.session.get("photo_scanned") else None,
        "lip_contours": profile.get("lip_contours") if request.session.get("photo_scanned") else None,
    })


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


def feedback_success(request):
    return render(request, "consumer/feedback_success.html", {
        "last_feedback": request.session.get("last_feedback", {}),
    })


def how_it_works(request):
    return render(request, "consumer/how_it_works.html")
