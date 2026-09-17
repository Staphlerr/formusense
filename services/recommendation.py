"""Shade recommendation: deterministic, research-grounded scoring.

No AI call happens in this module. Every scoring signal below is either
(a) the wearer's own stated preference (color/finish/intensity from
PreferenceForm -- just applying what they told us, not a research claim),
or (b) a numeric color-science metric computed from measured CIELAB values
when available, grounded in the references below -- or (c) the existing
"undertone_fit" categorical rule, explicitly disclosed as an INDUSTRY
CONVENTION (personal color analysis / "seasonal color theory"), not a
peer-reviewed, empirically validated causal claim. All three kinds of
signal are kept because a 24-hour prototype should use what's available,
but they must not be presented to judges as equally rigorous -- they are not.

References (peer-reviewed, used to justify the CONTRAST and HUE-HARMONY
metrics below):
- Russell, R. (2009). "A Sex Difference in Facial Contrast and its
  Exaggeration by Cosmetics." Perception, 38(8), 1211-1219.
  DOI: 10.1068/p6331. Measured luminance contrast between lips/eyes and
  surrounding skin; cosmetics increase this contrast, read as more
  feminine/attractive.
- Jones, A.L., Russell, R., Ward, R. (2015). "Cosmetics Alter
  Biologically-Based Factors of Beauty: Evidence from Facial Contrast."
  Evolutionary Psychology. DOI: 10.1177/147470491501300113. Replicates and
  extends the facial-contrast finding above.
- Kobayashi, Y., Matsushita, S., Morikawa, K. (2017). "Effects of Lip
  Color on Perceived Lightness of Human Facial Skin." i-Perception, 8(6).
  DOI: 10.1177/2041669517717500. Quantified: redder lips make skin look
  lighter (t(19)=2.94, p=.017); darker lips make skin look darker
  (t(19)=4.03, p=.004).
- Dong et al. (2025). "Applicability of Complementary Colors in Skin Tone
  Correction for Young Chinese Adults Based on Image Processing and
  Machine Learning." Journal of Cosmetic Dermatology. DOI: 10.1111/jocd.70566.
  Precedent for computing a hue/complementary-color relationship
  numerically rather than from a category label. (Bibliographic details
  confirmed via PubMed/Wiley; full methodology could not be fetched in
  this conversation due to an access block -- do not over-claim beyond
  what's stated here.)

Honesty note on what these metrics DO NOT claim: none of the papers above
studied lipstick-shade-to-skin-tone MATCHING or attractiveness preference
directly. They establish that (a) lip-skin lightness contrast is a real,
measurable, perceptually meaningful quantity, and (b) lip color causally
shifts perceived skin lightness in a specific, measured direction. We use
those facts to build a more defensible SCORING metric (aligning measured
contrast with the wearer's stated intensity preference) than an arbitrary
"bold = dark" assumption -- this is an application of the research, not a
restatement of a finding the research itself made about shade matching.
"""

from __future__ import annotations

import math

from services.color_science import lab_from_hex
from services.data import shades


def _hue_angle(a: float, b: float) -> float:
    return math.degrees(math.atan2(b, a)) % 360


def _metrics(shade: dict, profile: dict) -> dict:
    """Raw numbers behind the scoring below -- also handed to the optional
    AI personalization layer (ai_client.refine_shade_pick) as evidence, and
    to profile/recommendation templates for a "show your work" display.

    Returns {} when the profile has no measured Lab (demo/manual profiles,
    or a profile that came from ai_client.analyze_photo, which returns
    categories but not raw color values) -- callers must handle that case,
    not assume metrics are always present.
    """
    measurement = profile.get("measurement")
    if not measurement:
        return {}
    skin_lab = measurement["skin_lab"]
    shade_lab = lab_from_hex(shade["hex"])
    contrast = round(abs(skin_lab[0] - shade_lab[0]), 1)
    skin_chroma = (skin_lab[1] ** 2 + skin_lab[2] ** 2) ** 0.5
    hue_diff = None
    if skin_chroma >= 6:  # below this, hue angle is noise on near-neutral skin tone
        skin_hue = _hue_angle(skin_lab[1], skin_lab[2])
        shade_hue = _hue_angle(shade_lab[1], shade_lab[2])
        raw_diff = abs(skin_hue - shade_hue) % 360
        hue_diff = round(min(raw_diff, 360 - raw_diff), 1)
    return {
        "contrast": contrast,
        "hue_diff": hue_diff,
        "shade_lab": tuple(round(v, 1) for v in shade_lab),
    }


def _contrast_score(contrast: float, intensity_preference: str) -> float:
    """Score how well a candidate's measured lip-skin L* contrast matches
    the wearer's stated intensity preference. Grounded in Russell (2009) /
    Jones et al. (2015): higher contrast reads as more "made up"/dramatic;
    Kobayashi et al. (2017): direction and rough magnitude of lip-color
    effects on perceived skin lightness are real and measurable. The
    specific numeric ranges below are OUR chosen bands for this prototype,
    not values taken from either paper -- say so if asked.
    """
    target_ranges = {"natural": (4, 16), "medium": (14, 26), "bold": (24, 45)}
    lo, hi = target_ranges.get(intensity_preference, (10, 30))
    if lo <= contrast <= hi:
        return 4.0
    return max(0.0, 4.0 - min(abs(contrast - lo), abs(contrast - hi)) / 5)


def _harmony_score(hue_diff: float, role: str) -> float:
    """Score a candidate's hue relationship to the wearer's skin undertone.

    "daily" rewards a SMALL hue difference (analogous -- theorized in
    general color theory, e.g. Itten, to read as blending naturally with
    one's own coloring). "bold" rewards a LARGE hue difference
    (complementary/contrasting -- a statement look). This directional
    choice follows common color-theory practice and the general approach
    of computing hue relationships numerically (cf. Dong et al. 2025), but
    is NOT itself a claim that either direction is empirically proven more
    attractive -- no paper we found tested that for lipstick specifically.
    """
    if role == "daily":
        return 3.0 if hue_diff <= 40 else max(0.0, 3.0 - (hue_diff - 40) / 25)
    if role == "bold":
        return 3.0 if hue_diff >= 120 else max(0.0, 3.0 - (120 - hue_diff) / 25)
    return 1.5


def _score(shade: dict, profile: dict, preference: dict, role: str) -> float:
    score = 0.0
    undertone = profile.get("undertone", "neutral")
    fit = shade["undertone_fit"]
    has_measurement = bool(profile.get("measurement"))
    # Industry-convention categorical rule (personal color analysis) -- see
    # module docstring. Weighted less heavily when we have real measured
    # Lab values to compute the metrics below instead, since those are
    # closer to something we can actually defend as "computed", not "folk
    # convention".
    if undertone == fit:
        score += 3 if has_measurement else 5
    elif undertone in fit or fit in {"neutral", "warm_olive"} and undertone in {"warm", "olive"}:
        score += 2 if has_measurement else 3

    metrics = _metrics(shade, profile)
    if metrics:
        score += _contrast_score(metrics["contrast"], preference.get("intensity", ""))
        if metrics["hue_diff"] is not None:
            score += _harmony_score(metrics["hue_diff"], role)

    if shade["color_family"] == preference.get("color", ""):
        score += 5
    if shade["finish"] == preference.get("finish", ""):
        score += 2
    intensity_preference = preference.get("intensity", "")
    if intensity_preference == "natural" and shade["intensity"] in {"light", "light-medium"}:
        score += 2
    elif intensity_preference == "medium" and shade["intensity"] in {"medium", "medium-high"}:
        score += 2
    elif intensity_preference == "bold" and shade["intensity"] == "bold":
        score += 2
    if profile.get("lip_pigmentation") in {"medium_high", "high"} and shade["intensity"] in {"medium-high", "bold"}:
        score += 2
    if profile.get("skin_tone") in {"tan", "deep"} and shade["intensity"] == "light":
        score -= 2
    if profile.get("skin_tone") == "deep" and shade["intensity"] in {"medium-high", "bold"}:
        score += 2
    if any(word in profile.get("visible_lip_condition", "").lower() for word in {"dry", "kering"}):
        score += 2 if shade["finish"] in {"satin", "cream"} else -2 if shade["finish"] == "matte" else 0
    family = shade["color_family"]
    intensity = shade["intensity"]
    if role == "daily":
        score += 6 if family == "nude" else 0
        score += 2 if intensity in {"light", "light-medium", "medium"} else 0
    elif role == "energized":
        score += 6 if family == "terracotta" else 5 if family in {"coral", "pink"} else 0
        score += 2 if intensity in {"medium", "medium-high"} else 0
    else:
        score += 6 if intensity == "bold" else 0
        score += 2 if family in {"red", "berry"} else 0
    return score


def top_candidates(pool: list[dict], profile: dict, preference: dict, role: str, n: int = 3) -> list[dict]:
    """Top-n shades for a role, each carrying its score and raw metrics.

    This is the deterministic shortlist that the optional AI personalization
    layer (personalize() below) is allowed to choose from -- and ONLY from.
    """
    scored = [
        {**shade, "role": role, "score": round(_score(shade, profile, preference, role), 2),
         "metrics": _metrics(shade, profile)}
        for shade in pool
    ]
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:n]


def recommend(profile: dict, preference: dict) -> list[dict]:
    """Return three distinct, currently available demo shades, ranked by
    the deterministic color-science score above. No AI call happens here.

    Each returned pick also carries a "candidates" key (its top-3
    shortlist with scores/metrics) so an optional call to personalize()
    afterwards can personalize the final pick without re-deriving any
    color science -- see personalize()'s docstring.
    """
    pool = shades(available_only=True)
    results = []
    chosen_ids = set()
    for role, label in [
        ("daily", "Daily Natural"),
        ("energized", "Energized Vibe"),
        ("bold", "Bold Statement"),
    ]:
        remaining = [row for row in pool if row["shade_id"] not in chosen_ids]
        candidates = top_candidates(remaining, profile, preference, role, n=3)
        picked = candidates[0]
        chosen_ids.add(picked["shade_id"])
        results.append({
            **picked,
            "role_label": label,
            "reason": _reason(picked, profile, preference, picked.get("metrics")),
            "candidates": candidates,
            "personalized_by_ai": False,
        })
    return results


def personalize(picks: list[dict], profile: dict, preference: dict) -> list[dict]:
    """Optional, tightly-bounded AI personalization layer on top of
    recommend()'s deterministic ranking.

    This is the "Claude does optimization, not prediction from scratch"
    piece: services.ai_client.refine_shade_pick is only allowed to choose
    among the candidates recommend() ALREADY scored and validated for that
    role -- it cannot invent a shade, cannot see or touch the scoring
    math, and any invalid/unavailable response silently keeps the
    deterministic pick. Call this AFTER recommend(); if you skip it
    entirely (e.g. AI budget/latency reasons for a demo), recommend()'s
    output is already a complete, correct result on its own.

    NOTE ON LATENCY: this makes up to one AI call per role (up to 3 calls,
    each with its own ~12s timeout in ai_client). For a live demo where
    speed matters more than the personalization touch, it's reasonable to
    skip calling this and just use recommend()'s output directly.
    """
    from services.ai_client import AIUnavailable, refine_shade_pick  # local import: keep

    used_ids = set()
    refined = []
    for pick in picks:
        role, role_label = pick["role"], pick["role_label"]
        candidates = pick.get("candidates") or [pick]
        final, personalized = pick, False
        try:
            shade_id, ai_reason = refine_shade_pick(role_label, candidates, profile, preference)
            if shade_id != pick["shade_id"] and shade_id not in used_ids:
                replacement = next((c for c in candidates if c["shade_id"] == shade_id), None)
                if replacement is not None:
                    final = {**replacement, "role": role, "role_label": role_label,
                             "reason": ai_reason, "candidates": candidates}
                    personalized = True
        except AIUnavailable:
            pass  # deterministic pick stands -- this layer is strictly additive
        final["personalized_by_ai"] = personalized
        used_ids.add(final["shade_id"])
        refined.append(final)
    return refined


def _reason(shade: dict, profile: dict, preference: dict, metrics: dict | None = None) -> str:
    parts = [f"Warna {shade['color_family']} dengan hasil {shade['finish']}."]
    if shade["undertone_fit"] == profile.get("undertone"):
        parts.append("Arah warnanya sesuai konvensi personal color analysis untuk undertone yang terukur.")
    if shade["finish"] == preference.get("finish"):
        parts.append("Hasil akhirnya sesuai preferensimu.")
    if metrics and metrics.get("contrast") is not None:
        parts.append(f"Kontras terukur dengan kulitmu sekitar {metrics['contrast']} unit L* (CIELAB).")
    return " ".join(parts)