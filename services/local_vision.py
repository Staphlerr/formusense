"""Local, provisional cosmetic photo analysis for the hackathon prototype.

Face landmarks come from Google's MediaPipe FaceLandmarker (Tasks API).
Skin-tone classification and the CIELAB reference swatches come from
services/color_science.py -- this module does NOT keep its own copy of the
Monk Skin Tone hex values or skin-tone bucketing, so there is one source of
truth for that part of the pipeline. Undertone and lip-pigmentation
classification stay local to this module (see the note below the imports
for why those two were NOT also merged into color_science.py).

Colour categories below are transparent demo heuristics, not a trained
skin-tone or undertone classifier. Nothing here calls any AI/LLM API --
generative AI (services/ai_client.py) is only used afterwards, to phrase a
sentence about a profile this module already produced.
"""

from __future__ import annotations

import io
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from django.conf import settings
from PIL import Image, ImageOps, UnidentifiedImageError

from services.color_science import classify_skin_tone, classify_undertone


# Same file you already downloaded per services/color_science.py's earlier
# setup instructions -- services/models/face_landmarker.task. Both modules
# now agree on this single location; nothing to re-download.
MODEL_PATH = Path(settings.BASE_DIR) / "services" / "models" / "face_landmarker.task"
# NOTE: earlier drafts of this module used Path(settings.BASE_DIR) /
# "models" (project root, not inside services/). Standardized on the path
# above because that's where the model was already downloaded and
# confirmed working per services/color_science.py's original setup
# instructions -- no need to download the file a second time.

# Ordered Face Landmarker contour indices from Google's face mesh topology.
OUTER_LIP = (61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291,
             409, 270, 269, 267, 0, 37, 39, 40, 185)
INNER_LIP = (78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308,
             415, 310, 311, 312, 13, 82, 81, 80, 191)


class LocalVisionError(Exception):
    """A photo cannot be analysed reliably; manual input remains available.

    Callers (consumer/views.py) should catch this and fall back to
    services.ai_client.analyze_photo (AI vision, secondary), and finally to
    the manual profile form -- the same three-step fallback philosophy used
    elsewhere in this app. This module never calls an AI/LLM API itself.
    """


def model_available() -> bool:
    return MODEL_PATH.is_file() and MODEL_PATH.stat().st_size > 1_000_000


def create_face_landmarker():
    """Create one detector; batch callers may reuse it within a context manager."""
    options = mp.tasks.vision.FaceLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(MODEL_PATH)),
        running_mode=mp.tasks.vision.RunningMode.IMAGE,
        num_faces=2,
        min_face_detection_confidence=0.6,
        min_face_presence_confidence=0.6,
    )
    return mp.tasks.vision.FaceLandmarker.create_from_options(options)


def _read_photo(photo_bytes: bytes) -> np.ndarray:
    try:
        with Image.open(io.BytesIO(photo_bytes)) as image:
            if image.format not in {"JPEG", "PNG"}:
                raise LocalVisionError("Gunakan foto JPG atau PNG.")
            if image.width * image.height > 16_000_000:
                raise LocalVisionError("Resolusi foto terlalu besar. Gunakan foto hingga 16 megapiksel.")
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
            return np.asarray(image).copy()
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise LocalVisionError("Foto tidak dapat dibaca. Coba JPG atau PNG lain.") from error


def _polygon(landmarks, indices, width: int, height: int) -> np.ndarray:
    return np.asarray([
        (round(landmarks[index].x * width), round(landmarks[index].y * height))
        for index in indices
    ], dtype=np.int32)


def _median_lab(lab: np.ndarray, mask: np.ndarray) -> np.ndarray:
    pixels = lab[mask > 0]
    if pixels.shape[0] < 40:
        raise LocalVisionError("Area wajah terlalu kecil. Ambil foto lebih dekat dan terang.")
    return np.median(pixels, axis=0)


def _skin_mask(shape: tuple[int, ...], landmarks) -> np.ndarray:
    height, width = shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)
    face_width = abs(landmarks[454].x - landmarks[234].x) * width
    radius = max(3, round(face_width * 0.035))
    # Cheek regions stay away from eyes, hair and the lips on a frontal face.
    for index in (50, 280):
        point = landmarks[index]
        center = (round(point.x * width), round(point.y * height))
        cv2.circle(mask, center, radius, 255, thickness=-1)
    return mask


def _lip_mask(shape: tuple[int, ...], landmarks) -> np.ndarray:
    height, width = shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillPoly(mask, [_polygon(landmarks, OUTER_LIP, width, height)], 255)
    cv2.fillPoly(mask, [_polygon(landmarks, INNER_LIP, width, height)], 0)
    return mask


# Undertone classification now delegates to services.color_science.classify_undertone
# (b*/a* hue-ratio rule, referenced to Van Song et al. 2026 / the personal
# color analysis literature -- see that function's docstring) instead of
# keeping a second, ad-hoc local threshold set. That function never returns
# "uncertain" -- it resolves low-chroma cases to "neutral" instead, which is
# both a real category in this app's form choices and a more literature-
# grounded outcome than an unexplained "uncertain". The exposure/chroma
# guards below (skin_l range, chroma < 3) still run first and independently
# decide when a photo is unreliable enough to skip color classification
# altogether -- that's a data-quality check, not an undertone rule.


def _pigmentation_from_contrast(skin_l: float, lip_l: float) -> str:
    # Kept local (not color_science.classify_lip_pigmentation) -- see that
    # function's docstring note on the two different threshold sets.
    contrast = skin_l - lip_l
    if contrast < 3:
        return "low"
    if contrast < 9:
        return "medium"
    if contrast < 17:
        return "medium_high"
    return "high"


def analyze_photo_local(photo_bytes: bytes, mime_type: str, *, face_landmarker=None) -> dict:
    """Return editable estimates and normalized lip contours; never store a photo."""
    if mime_type not in {"image/jpeg", "image/png"}:
        raise LocalVisionError("Gunakan foto JPG atau PNG.")
    if not model_available():
        raise LocalVisionError("Model deteksi wajah lokal belum tersedia.")
    rgb = _read_photo(photo_bytes)
    height, width = rgb.shape[:2]
    if min(height, width) < 240:
        raise LocalVisionError("Resolusi foto terlalu kecil untuk mendeteksi bibir.")

    try:
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        if face_landmarker is None:
            with create_face_landmarker() as landmarker:
                result = landmarker.detect(image)
        else:
            result = face_landmarker.detect(image)
    except Exception as error:
        raise LocalVisionError("Analisis lokal belum berhasil. Gunakan profil manual atau foto lain.") from error
    if not result.face_landmarks:
        raise LocalVisionError("Wajah tidak terdeteksi. Ambil foto dari depan dengan cahaya merata.")
    if len(result.face_landmarks) != 1:
        raise LocalVisionError("Ada lebih dari satu wajah. Gunakan foto satu orang saja.")
    landmarks = result.face_landmarks[0]
    if any(not 0 <= landmarks[index].x <= 1 or not 0 <= landmarks[index].y <= 1
           for index in OUTER_LIP + INNER_LIP):
        raise LocalVisionError("Bibir terlalu dekat dengan tepi foto. Ambil foto sedikit lebih jauh.")

    contours = {
        "outer": [[round(landmarks[i].x, 5), round(landmarks[i].y, 5)] for i in OUTER_LIP],
        "inner": [[round(landmarks[i].x, 5), round(landmarks[i].y, 5)] for i in INNER_LIP],
    }
    profile = {
        "skin_tone": "uncertain",
        "undertone": "uncertain",
        "lip_pigmentation": "uncertain",
        "visible_lip_condition": "",
        "confidence": "local_low",
        "lip_contours": contours,
        "analysis_note": "Kontur bibir terdeteksi. Sesuaikan nilai warna di bawah bila diperlukan.",
    }
    lab = cv2.cvtColor(rgb.astype(np.float32) / 255.0, cv2.COLOR_RGB2LAB)
    try:
        skin = _median_lab(lab, _skin_mask(rgb.shape, landmarks))
        lips = _median_lab(lab, _lip_mask(rgb.shape, landmarks))
    except LocalVisionError:
        return profile

    skin_l, skin_a, skin_b = (float(value) for value in skin)
    lip_l, lip_a, lip_b = (float(value) for value in lips)
    # Reject severely under/overexposed photos instead of inventing colour labels.
    if not 18 <= skin_l <= 88:
        profile["analysis_note"] = "Pencahayaan foto membuat warna sulit diperkirakan. Isi warna secara manual."
        return profile
    if (skin_a ** 2 + skin_b ** 2) ** 0.5 < 3:
        profile["analysis_note"] = "Foto ini nyaris tidak memuat informasi warna. Isi warna secara manual."
        return profile

    skin_tone_label, mst_index, mst_distance = classify_skin_tone((skin_l, skin_a, skin_b))
    undertone_label = classify_undertone((skin_l, skin_a, skin_b))
    profile.update({
        "skin_tone": skin_tone_label,
        "undertone": undertone_label,
        "lip_pigmentation": _pigmentation_from_contrast(skin_l, lip_l),
        "confidence": "local_estimate",
        "analysis_note": "Estimasi warna dari foto ini. Sesuaikan bila kurang tepat.",
        # Raw numbers behind the categorical labels above, for transparency /
        # evidence display -- "not a black box" is only true if these are
        # actually shown somewhere (e.g. profile_result.html).
        "measurement": {
            "method": "mediapipe_face_landmarker+cielab(opencv)",
            "monk_skin_tone_index": mst_index,
            "monk_skin_tone_distance": round(mst_distance, 2),
            "skin_lab": (round(skin_l, 1), round(skin_a, 1), round(skin_b, 1)),
            "lip_lab": (round(lip_l, 1), round(lip_a, 1), round(lip_b, 1)),
        },
    })
    return profile