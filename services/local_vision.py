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

from services.color_science import classify_skin_tone


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


def _undertone_from_lab(a_star: float, b_star: float) -> str:
    # Only strong yellow/red balance is labelled. Most photos stay uncertain
    # because white balance and illumination change these values substantially.
    # Kept local rather than calling color_science.classify_undertone: that
    # function never returns "uncertain", which this app's forms expect as a
    # valid fallback category -- see color_science.py's docstring note.
    if a_star <= 0 or b_star <= 0:
        return "uncertain"
    ratio = b_star / a_star
    if ratio >= 1.85 and b_star >= 18:
        return "warm"
    if ratio <= 0.78 and a_star >= 15:
        return "cool"
    return "uncertain"


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


def analyze_photo_local(photo_bytes: bytes, mime_type: str) -> dict:
    """Return editable estimates and normalized lip contours; never store a photo."""
    if mime_type not in {"image/jpeg", "image/png"}:
        raise LocalVisionError("Gunakan foto JPG atau PNG.")
    if not model_available():
        raise LocalVisionError("Model deteksi wajah lokal belum tersedia.")
    rgb = _read_photo(photo_bytes)
    height, width = rgb.shape[:2]
    if min(height, width) < 240:
        raise LocalVisionError("Resolusi foto terlalu kecil untuk mendeteksi bibir.")

    options = mp.tasks.vision.FaceLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path=str(MODEL_PATH)),
        running_mode=mp.tasks.vision.RunningMode.IMAGE,
        num_faces=2,
        min_face_detection_confidence=0.6,
        min_face_presence_confidence=0.6,
    )
    try:
        with mp.tasks.vision.FaceLandmarker.create_from_options(options) as landmarker:
            result = landmarker.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
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
        "analysis_note": "Kontur bibir terdeteksi lokal. Warna dapat berubah karena cahaya dan kamera; periksa profil ini.",
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
        profile["analysis_note"] = "Kontur terdeteksi, tetapi pencahayaan membuat warna sulit diperkirakan. Isi profil manual."
        return profile

    skin_tone_label, mst_index, mst_distance = classify_skin_tone((skin_l, skin_a, skin_b))
    profile.update({
        "skin_tone": skin_tone_label,
        "undertone": _undertone_from_lab(skin_a, skin_b),
        "lip_pigmentation": _pigmentation_from_contrast(skin_l, lip_l),
        "confidence": "local_estimate",
        "analysis_note": "Perkiraan dari warna area pipi dan kontras bibir-kulit pada foto ini. Periksa dan koreksi jika meleset.",
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