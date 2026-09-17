"""Pure color-science math: sRGB/CIELAB conversion and reference-scale classification.

DROP-IN LOCATION: services/color_science.py

This module intentionally contains ONLY deterministic math and published
reference data -- no photo decoding, no face/landmark detection, no I/O.
Face/landmark detection and pixel sampling live in services/local_vision.py
(MediaPipe FaceLandmarker + OpenCV lip/cheek masking); that module imports
the classify_* functions and MONK_SKIN_TONE_HEX from here so there is a
single source of truth for the reference swatches and thresholds, instead
of two modules quietly drifting apart with slightly different numbers.

Nothing here is invented: every number produced can be traced back to
(a) a pixel value actually read from a photo (by the caller, typically
services/local_vision.py), and (b) a published reference point or a
documented, simplified color-theory rule. Generative AI (see
services/ai_client.py) is not used anywhere in this module -- it is only
used AFTER a profile like this has been produced, purely to phrase a
sentence about it (see ai_client.generate_personal_note).

References:
- Monk Skin Tone Scale, 10 published reference tones (Google / Ellis Monk,
  Harvard). https://skintone.google/the-scale
- CIELAB color space (CIE 1976), the standard perceptual color space used
  in most skin-tone classification literature, e.g. Van Song et al.,
  "A New Method for Skin Color Classification Based on Global CIELAB Data
  and k-Mean Clustering", Color Research & Application (2026).

Honesty note on this file's history: an earlier version of this module also
contained its own MediaPipe detection + pixel-sampling code
(_locate_regions / analyze_photo_objective). That has been removed in favor
of services/local_vision.py's more careful implementation (full lip-contour
masking instead of 4 hand-picked points, adaptive cheek-sampling radius,
multi-face detection) -- no point maintaining two parallel detection
pipelines that can silently disagree. If you still have consumer/views.py
importing LandmarkNotFound / analyze_photo_objective from this module,
switch it to services.local_vision's LocalVisionError / analyze_photo_local
per the updated views.py.
"""

from __future__ import annotations


# --- Monk Skin Tone Scale reference swatches -------------------------------
# Published values, lightest (index 0) to darkest (index 9). Source: Google's
# Monk Skin Tone Scale (https://skintone.google/the-scale); cross-checked
# against the tabulated values on
# https://en.wikipedia.org/wiki/Monk_Skin_Tone_Scale. (A second, independent
# implementation of this module briefly used a very slightly different hex
# set, apparently sourced from an FDA presentation reproducing the same
# scale -- the differences were sub-perceptual rounding, but only ONE set
# should be used app-wide, which is why this is now the single source of
# truth. Re-verify against the live page before a high-stakes submission --
# do not trust this comment blindly either.)
MONK_SKIN_TONE_HEX = [
    "#f6ede4", "#f3e7db", "#f7ead0", "#eadaba", "#d7bd96",
    "#a07e56", "#825c43", "#604134", "#3a312a", "#292420",
]

# Coarse mapping from the 10-point MST scale down to this app's existing
# skin_tone categories (light/light_medium/medium/tan/deep), so both
# services/local_vision.py and (previously) this module's own detector
# produce identical category labels for the same measured color.
# This bucketing is OUR choice (documented here, not hidden), not part of
# the published MST scale itself.
_MST_TO_APP_SKIN_TONE = {
    0: "light", 1: "light",
    2: "light_medium", 3: "light_medium",
    4: "medium", 5: "medium",
    6: "tan", 7: "tan",
    8: "deep", 9: "deep",
}


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
    formula this follows. (services/local_vision.py instead uses OpenCV's
    built-in sRGB->Lab conversion for its own pixel sampling, which is an
    equally standard, well-tested implementation of the same CIE formula --
    just less manually inspectable in this codebase. Both are legitimate;
    this hand-rolled version exists so at least one code path has zero
    library dependency for the core color math, and so formula_lab.py can
    reuse it for shade<->recipe matching without importing OpenCV.)
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


def lab_from_hex(hex_color: str) -> tuple[float, float, float]:
    """Convenience wrapper: hex string straight to CIELAB. Used by
    services/recommendation.py (shade<->skin contrast/harmony metrics) and
    services/formula_lab.py (recipe matching) so neither module needs its
    own hex-parsing code.
    """
    return srgb_to_lab(*_hex_to_srgb(hex_color))


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

    NOTE: services/local_vision.py currently keeps its OWN undertone
    heuristic (_undertone_from_lab) rather than calling this function,
    because it needs to return "uncertain" as a valid category (matching
    this app's form choices) and this function does not produce that value
    -- see the module docstring in local_vision.py for why the two were not
    merged.
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

    NOTE: services/local_vision.py currently keeps its OWN version of this
    (_pigmentation_from_contrast) with tighter thresholds (3/9/17 instead of
    8/18/28) -- possibly tuned against real sample photos, which would make
    them more empirically grounded than the thresholds below (chosen without
    real photo data). Neither set is a literature value; pick one canonical
    set once you've checked both against real photos, rather than leaving
    two silently different scales in the codebase.
    """
    contrast = skin_lab[0] - lip_lab[0]  # positive = lips darker than skin
    if contrast < 8:
        return "low"
    if contrast < 18:
        return "medium"
    if contrast < 28:
        return "medium_high"
    return "high"