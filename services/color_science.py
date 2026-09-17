"""Objective, explainable skin/lip color measurement.

DROP-IN LOCATION: services/color_science.py

This module replaces "ask a vision-language model to guess the skin tone"
with a deterministic pipeline: detect facial landmarks with a specialized,
pre-trained computer-vision model (MediaPipe Face Mesh), sample real pixel
colors at those landmarks, convert them into a perceptually-uniform color
space (CIELAB, the standard used in color science), and classify the result
against a published, citable reference scale.

Nothing here is invented: every number produced can be traced back to
(a) a pixel value actually read from the uploaded photo, and (b) a
published reference point or a documented, simplified color-theory rule.
Generative AI (see services/ai_client.py) is not used anywhere in this
module -- it is only used AFTER this module has produced a profile, purely
to phrase a sentence about it (see ai_client.generate_personal_note).

References:
- Monk Skin Tone Scale, 10 published reference tones (Google / Ellis Monk,
  Harvard). https://skintone.google/the-scale
- CIELAB color space (CIE 1976), the standard perceptual color space used
  in most skin-tone classification literature, e.g. Van Song et al.,
  "A New Method for Skin Color Classification Based on Global CIELAB Data
  and k-Mean Clustering", Color Research & Application (2026).
- MediaPipe Face Landmarker / Tasks API (Google Research) -- pre-trained
  facial landmark model (478-point face topology, an extension of the
  original 468-point Face Mesh with 10 added iris points); see
  https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker
  for the model and its canonical landmark index map.

IMPORTANT -- read before the demo:
This module targets MediaPipe's newer Tasks API (`FaceLandmarker`), not the
older "Legacy Solutions" API (`mp.solutions.face_mesh`). As of mediapipe
1.0.x the legacy Solutions API has been removed from the package entirely,
so this module downloads/loads a `.task` model file instead of relying on
a pip-bundled model. Before the demo:
1. Create a `services/models/` folder and download the model file once
   from Google's official model bucket:
   https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task
   and save it as `services/models/face_landmarker.task`
   (i.e. next to this file, in a `models/` subfolder).
2. The MediaPipe landmark index used below for cheek/skin sampling (205)
   is a commonly-cited cheek point in MediaPipe tutorials, but it has NOT
   been executed/verified in this conversation (no mediapipe runtime
   available here). Run it on 3-5 real sample photos, draw the sampled
   skin/lip points on the image, and eyeball that the skin point actually
   lands on cheek skin (not hair, background, or shadow) and the lip
   points land on the lips. If it drifts, adjust `_CHEEK_LANDMARK_INDEX`
   or `_LIP_LANDMARK_INDICES` -- do not assume they are correct without
   checking.
3. Unlike the old `FACEMESH_LIPS` connection set (which no longer exists
   in the Tasks API), lip geometry here comes from four hand-picked
   landmark indices (61/291/0/17 -- left corner/right corner/upper outer
   lip/lower outer lip). These are standard, commonly-documented indices
   in MediaPipe's 468/478-point face topology, but "commonly documented"
   is not the same as "verified by us in this project" -- check them
   against real photos same as the cheek point.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image


class LandmarkNotFound(Exception):
    """Raised when a face/lips cannot be located reliably in the photo.

    Callers should catch this and fall back to services.ai_client.analyze_photo
    (AI vision, secondary), and finally to the manual profile form -- the
    same three-step fallback philosophy already used elsewhere in this app.
    """


# --- Monk Skin Tone Scale reference swatches -------------------------------
# Published values, lightest (index 0) to darkest (index 9). Source: Google's
# Monk Skin Tone Scale (https://skintone.google/the-scale); the scale page is
# JS-rendered, so these were cross-checked against the tabulated values on
# https://en.wikipedia.org/wiki/Monk_Skin_Tone_Scale. Re-verify against the
# live page before a high-stakes submission -- do not trust this comment
# blindly either.
MONK_SKIN_TONE_HEX = [
    "#f6ede4", "#f3e7db", "#f7ead0", "#eadaba", "#d7bd96",
    "#a07e56", "#825c43", "#604134", "#3a312a", "#292420",
]

# Coarse mapping from the 10-point MST scale down to this app's existing
# skin_tone categories (light/light_medium/medium/tan/deep), so this module
# is a drop-in replacement for the AI-vision output shape used elsewhere.
# This bucketing is OUR choice (documented here, not hidden), not part of
# the published MST scale itself.
_MST_TO_APP_SKIN_TONE = {
    0: "light", 1: "light",
    2: "light_medium", 3: "light_medium",
    4: "medium", 5: "medium",
    6: "tan", 7: "tan",
    8: "deep", 9: "deep",
}

_CHEEK_LANDMARK_INDEX = 205  # verify against mediapipe's face mesh map -- see module docstring

# Hand-picked lip landmark indices in MediaPipe's 468/478-point face
# topology (the Tasks API no longer exposes a named FACEMESH_LIPS
# connection set, so these replace it). See module docstring point 3.
_LIP_LANDMARK_INDICES = {
    "left": 61,    # left mouth corner
    "right": 291,  # right mouth corner
    "top": 0,      # upper outer lip midpoint
    "bottom": 17,  # lower outer lip midpoint
}

# Location of the downloaded MediaPipe Tasks model file. See module
# docstring step 1 for the download URL and expected path.
_MODEL_PATH = Path(__file__).resolve().parent / "models" / "face_landmarker.task"


def _hex_to_srgb(hex_color: str) -> tuple[float, float, float]:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return r, g, b


def _srgb_channel_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def srgb_to_lab(r: float, g: float, b: float) -> tuple[float, float, float]:
    """Convert sRGB (0-1 range per channel) to CIELAB (D65 illuminant, CIE 1976).

    Implemented as the plain textbook formula (no library black box) so
    every step is inspectable and citable. See
    https://en.wikipedia.org/wiki/CIELAB_color_space for the reference
    formula this follows.
    """
    rl, gl, bl = (_srgb_channel_to_linear(c) for c in (r, g, b))
    x = rl * 0.4124 + gl * 0.3576 + bl * 0.1805
    y = rl * 0.2126 + gl * 0.7152 + bl * 0.0722
    z = rl * 0.0193 + gl * 0.1192 + bl * 0.9505
    # D65 reference white (standard illuminant)
    xn, yn, zn = 0.95047, 1.0, 1.08883

    def f(t):
        delta = 6 / 29
        return t ** (1 / 3) if t > delta ** 3 else t / (3 * delta ** 2) + 4 / 29

    fx, fy, fz = f(x / xn), f(y / yn), f(z / zn)
    lightness = 116 * fy - 16
    a = 500 * (fx - fy)
    b_ = 200 * (fy - fz)
    return lightness, a, b_


_MST_LAB = [srgb_to_lab(*_hex_to_srgb(h)) for h in MONK_SKIN_TONE_HEX]


def classify_skin_tone(lab: tuple[float, float, float]) -> tuple[str, int, float]:
    """Nearest Monk Skin Tone swatch by Euclidean distance in Lab space.

    Returns (app_skin_tone_label, mst_index_1_to_10, distance).

    Honesty note: this uses a simple Euclidean distance in Lab, not the more
    perceptually exact CIEDE2000 formula used in some color-science
    literature. That is a documented simplification appropriate for a
    24-hour prototype, not a claim of clinical-grade color-difference
    measurement -- say so if asked.
    """
    distances = [
        sum((a - b) ** 2 for a, b in zip(lab, ref)) ** 0.5 for ref in _MST_LAB
    ]
    nearest = min(range(len(distances)), key=lambda i: distances[i])
    return _MST_TO_APP_SKIN_TONE[nearest], nearest + 1, distances[nearest]


def classify_undertone(lab: tuple[float, float, float]) -> str:
    """Warm/cool/neutral/olive from the CIELAB a*/b* balance.

    Honesty note: this is a deliberately simple, fully documented heuristic
    -- NOT a trained classifier, and NOT a literal reproduction of any one
    paper's undisclosed numeric thresholds. It follows the general
    color-theory principle used in the literature reviewed for this project
    (e.g. Van Song et al. 2026, Color Research & Application; the personal
    color analysis field more broadly): a higher b*/a* ratio (more yellow
    relative to red-green) reads as warm, a low ratio reads as cool, very
    low chroma reads as neutral. The exact cutoff numbers below are tunable
    constants we chose for this prototype -- present them as such, not as an
    empirically validated universal threshold.
    """
    _, a, b = lab
    chroma = (a ** 2 + b ** 2) ** 0.5
    if chroma < 6:
        return "neutral"
    hue_ratio = b / (abs(a) + 1e-6)
    if hue_ratio > 2.2 and a > 8:
        return "olive"
    if hue_ratio > 1.3:
        return "warm"
    if hue_ratio < 0.6:
        return "cool"
    return "neutral"


def classify_lip_pigmentation(skin_lab, lip_lab) -> str:
    """Pigmentation relative to the wearer's OWN skin lightness.

    There is no published absolute global scale for "lip pigmentation
    level" -- perceived pigmentation is inherently about contrast against
    the wearer's own skin, so a relative measure is more defensible than an
    invented absolute one. Thresholds below are tunable prototype constants.
    """
    contrast = skin_lab[0] - lip_lab[0]  # positive = lips darker than skin
    if contrast < 8:
        return "low"
    if contrast < 18:
        return "medium"
    if contrast < 28:
        return "medium_high"
    return "high"


@dataclass
class _Regions:
    skin_rgb: tuple[float, float, float]
    lip_rgb: tuple[float, float, float]
    lip_points: dict


def _sample_patch(image: np.ndarray, x: float, y: float, radius_px: int = 6):
    """Average RGB (0-1 range) in a small square patch around (x, y),
    where x/y are relative image coordinates (0-1), matching the format
    already used for lip_points elsewhere in this app.
    """
    h, w, _ = image.shape
    cx, cy = int(x * w), int(y * h)
    x0, x1 = max(cx - radius_px, 0), min(cx + radius_px, w)
    y0, y1 = max(cy - radius_px, 0), min(cy + radius_px, h)
    patch = image[y0:y1, x0:x1].reshape(-1, 3)
    if patch.size == 0:
        raise LandmarkNotFound("Region sampel warna berada di luar batas gambar")
    mean = patch.mean(axis=0) / 255.0
    return float(mean[0]), float(mean[1]), float(mean[2])


def _locate_regions(image: np.ndarray) -> _Regions:
    """Run MediaPipe FaceLandmarker (Tasks API) and sample skin + lip pixel colors.

    NOTE: this targets mediapipe's newer Tasks API, required for mediapipe
    1.0.x where the legacy `mp.solutions.face_mesh` API has been removed.
    See the module docstring for the model download step this depends on.
    """
    try:
        import mediapipe as mp  # imported lazily: the rest of the app still
        # works even before this dependency is installed
    except ImportError as error:
        # Treat "dependency not installed yet" the same as "couldn't find a
        # face" -- callers (consumer/views.py) already catch LandmarkNotFound
        # and fall back to AI vision, then manual. Without this, a missing
        # mediapipe install turns into an unhandled 500 instead of a graceful
        # fallback, which defeats the whole point of the fallback chain.
        raise LandmarkNotFound(
            "Modul mediapipe belum terinstal (pip install mediapipe); "
            "jatuh ke fallback berikutnya"
        ) from error

    if not _MODEL_PATH.exists():
        # Fail gracefully (fallback chain) instead of an unhandled error --
        # but this is a one-time setup step, not a real "no face found", so
        # the message says exactly what to do.
        raise LandmarkNotFound(
            "Model MediaPipe (face_landmarker.task) belum ditemukan di "
            f"{_MODEL_PATH}. Unduh sekali dari "
            "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
            "face_landmarker/float16/1/face_landmarker.task dan simpan di "
            "path tersebut (lihat docstring modul ini) -- untuk sementara "
            "jatuh ke fallback berikutnya."
        )

    try:
        base_options_cls = mp.tasks.BaseOptions
        face_landmarker_cls = mp.tasks.vision.FaceLandmarker
        face_landmarker_options_cls = mp.tasks.vision.FaceLandmarkerOptions
        running_mode_enum = mp.tasks.vision.RunningMode
    except AttributeError as error:
        # This would mean the installed mediapipe is neither the legacy
        # Solutions API nor the Tasks API we now target -- don't guess
        # further, surface it clearly instead of silently misbehaving.
        raise LandmarkNotFound(
            "Versi mediapipe yang terinstal tidak menyediakan Tasks API "
            "(mp.tasks.vision.FaceLandmarker). Modul ini ditulis untuk "
            "mediapipe >= 1.0. Cek `pip show mediapipe` dan pastikan "
            "versinya kompatibel, jangan asumsikan."
        ) from error

    options = face_landmarker_options_cls(
        base_options=base_options_cls(model_asset_path=str(_MODEL_PATH)),
        running_mode=running_mode_enum.IMAGE,
        num_faces=1,
    )

    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=image)

    with face_landmarker_cls.create_from_options(options) as landmarker:
        result = landmarker.detect(mp_image)

    if not result.face_landmarks:
        raise LandmarkNotFound("Wajah tidak terdeteksi dengan jelas di foto")

    landmarks = result.face_landmarks[0]  # list of 478 landmarks, .x/.y/.z, normalized 0-1

    lip_lm = {name: landmarks[idx] for name, idx in _LIP_LANDMARK_INDICES.items()}
    lip_cx = sum(lm.x for lm in lip_lm.values()) / len(lip_lm)
    lip_cy = sum(lm.y for lm in lip_lm.values()) / len(lip_lm)

    cheek = landmarks[_CHEEK_LANDMARK_INDEX]

    lip_rgb = _sample_patch(image, lip_cx, lip_cy)
    skin_rgb = _sample_patch(image, cheek.x, cheek.y)

    lip_points = {
        "left": [lip_lm["left"].x, lip_lm["left"].y],
        "right": [lip_lm["right"].x, lip_lm["right"].y],
        "top": [lip_lm["top"].x, lip_lm["top"].y],
        "bottom": [lip_lm["bottom"].x, lip_lm["bottom"].y],
    }
    return _Regions(skin_rgb=skin_rgb, lip_rgb=lip_rgb, lip_points=lip_points)


def analyze_photo_objective(photo_bytes: bytes, mime_type: str) -> dict:
    """Primary, deterministic replacement for ai_client.analyze_photo.

    Returns the same dict shape the rest of the app already expects
    (skin_tone, undertone, lip_pigmentation, visible_lip_condition,
    confidence, lip_points), plus an extra "measurement" key with the raw
    numbers (for showing your work to judges / storing as evidence). Callers
    that only read the existing keys need no changes.

    Raises LandmarkNotFound if no face/lips could be located -- callers
    should catch that and fall back to services.ai_client.analyze_photo,
    then to the manual form, exactly like the existing AIUnavailable
    fallback chain already does.
    """
    del mime_type  # decoding is format-agnostic via PIL; kept for interface parity
    image = np.array(Image.open(io.BytesIO(photo_bytes)).convert("RGB"))
    regions = _locate_regions(image)

    skin_lab = srgb_to_lab(*regions.skin_rgb)
    lip_lab = srgb_to_lab(*regions.lip_rgb)

    skin_tone, mst_index, mst_distance = classify_skin_tone(skin_lab)
    undertone = classify_undertone(skin_lab)
    lip_pigmentation = classify_lip_pigmentation(skin_lab, lip_lab)

    return {
        "skin_tone": skin_tone,
        "undertone": undertone,
        "lip_pigmentation": lip_pigmentation,
        "visible_lip_condition": "",
        "confidence": "measured",
        "lip_points": regions.lip_points,
        "measurement": {
            "method": "mediapipe_face_landmarker+cielab",
            "monk_skin_tone_index": mst_index,
            "monk_skin_tone_distance": round(mst_distance, 2),
            "skin_lab": tuple(round(v, 1) for v in skin_lab),
            "lip_lab": tuple(round(v, 1) for v in lip_lab),
        },
    }