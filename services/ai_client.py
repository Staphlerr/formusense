"""Optional Sumopod adapters. Decisions and counts stay in local services."""

import base64
import json
import logging
import os
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


class AIUnavailable(Exception):
    pass


def analyze_photo(photo_bytes, mime_type):
    api_key = os.environ.get("AI_API_KEY", "")
    model = os.environ.get("AI_VISION_MODEL", "")
    if not api_key or not model:
        logger.warning(
            "AI vision belum dikonfigurasi (AI_API_KEY %s, AI_VISION_MODEL %s)",
            "ada" if api_key else "KOSONG", "ada" if model else "KOSONG",
        )
        raise AIUnavailable("Model vision atau kunci API belum dikonfigurasi")
    if mime_type not in {"image/jpeg", "image/png"}:
        raise AIUnavailable("Format foto harus JPG atau PNG")
    base_url = os.environ.get("AI_BASE_URL", "https://ai.sumopod.com/v1").rstrip("/")
    if not base_url.startswith("https://"):
        raise AIUnavailable("AI_BASE_URL harus memakai HTTPS")
    encoded = base64.b64encode(photo_bytes).decode("ascii")
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": (
                "Estimate visible cosmetic attributes only. Return JSON with keys: "
                "skin_tone (light/light_medium/medium/tan/deep/uncertain), "
                "undertone (warm/cool/neutral/olive/uncertain), "
                "lip_pigmentation (low/medium/medium_high/high/uncertain), "
                "visible_lip_condition (short cosmetic description), confidence (low/medium/high), "
                "and optional lip_points as left/top/right/bottom pairs of [x,y] numbers between "
                "0 and 1 relative to the ENTIRE image for a visual lipstick preview. "
                "Top and bottom must mark the OUTER LIP boundary, not nose or chin; "
                "the vertical lip span is normally smaller than the mouth width. "
                "If the lip outline is unclear, omit lip_points. "
                "If lighting or makeup prevents attribute assessment, use uncertain. No health diagnosis. "
                "Return raw JSON only, without Markdown fences."
            )},
            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{encoded}"}},
        ]}],
    }
    request = Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            data = json.load(response)
        content = data["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("AI response is not text")
        result = json.loads(content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip())
    except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
        logger.warning("Panggilan AI vision gagal: %r", error)
        raise AIUnavailable("Analisis foto gagal; gunakan profil manual") from error
    allowed = {
        "skin_tone": {"light", "light_medium", "medium", "tan", "deep", "uncertain"},
        "undertone": {"warm", "cool", "neutral", "olive", "uncertain"},
        "lip_pigmentation": {"low", "medium", "medium_high", "high", "uncertain"},
    }
    for field, choices in allowed.items():
        if result.get(field) not in choices:
            raise AIUnavailable("Hasil AI tidak sesuai format; gunakan profil manual")
    result["visible_lip_condition"] = str(result.get("visible_lip_condition", "Tidak diketahui"))[:120]
    result["confidence"] = result.get("confidence") if result.get("confidence") in {"low", "medium", "high"} else "low"
    points = result.get("lip_points")
    if isinstance(points, dict):
        cleaned = {}
        for name in ("left", "top", "right", "bottom"):
            pair = points.get(name)
            if not isinstance(pair, list) or len(pair) != 2:
                break
            try:
                x, y = (float(value) for value in pair)
            except (TypeError, ValueError):
                break
            if not (0 <= x <= 1 and 0 <= y <= 1):
                break
            cleaned[name] = [x, y]
        if len(cleaned) == 4 and cleaned["left"][0] < cleaned["right"][0] \
                and cleaned["top"][1] < cleaned["bottom"][1] \
                and cleaned["bottom"][1] - cleaned["top"][1] \
                <= (cleaned["right"][0] - cleaned["left"][0]) * 0.7 \
                and cleaned["left"][0] <= cleaned["top"][0] <= cleaned["right"][0] \
                and cleaned["left"][0] <= cleaned["bottom"][0] <= cleaned["right"][0]:
            result["lip_points"] = cleaned
        else:
            result.pop("lip_points", None)
    return result


def _text_completion(instructions, facts, max_tokens=180):
    api_key = os.environ.get("AI_API_KEY", "")
    model = os.environ.get("AI_TEXT_MODEL", "")
    if not api_key or not model:
        logger.warning(
            "AI text belum dikonfigurasi (AI_API_KEY %s, AI_TEXT_MODEL %s)",
            "ada" if api_key else "KOSONG", "ada" if model else "KOSONG",
        )
        raise AIUnavailable("Model text atau kunci API belum dikonfigurasi")
    base_url = os.environ.get("AI_BASE_URL", "https://ai.sumopod.com/v1").rstrip("/")
    if not base_url.startswith("https://"):
        raise AIUnavailable("AI_BASE_URL harus memakai HTTPS")
    payload = {
        "model": model, "temperature": 0.3, "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": json.dumps(facts, ensure_ascii=False)},
        ],
    }
    request = Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=12) as response:
            data = json.load(response)
        content = data["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("AI response is not text")
        note = content.strip()
        if not note:
            raise ValueError("Empty AI note")
        return note[:1200]
    except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
        logger.warning("Panggilan AI text gagal: %r", error)
        raise AIUnavailable("Catatan AI tidak tersedia") from error


def _json_completion(instructions, facts, max_tokens=200):
    """Like _text_completion, but parses the model's reply as JSON.

    Used by refine_shade_pick, which needs a structured choice back (a
    shade_id plus a short reason), not free text.
    """
    api_key = os.environ.get("AI_API_KEY", "")
    model = os.environ.get("AI_TEXT_MODEL", "")
    if not api_key or not model:
        logger.warning(
            "AI text belum dikonfigurasi (AI_API_KEY %s, AI_TEXT_MODEL %s)",
            "ada" if api_key else "KOSONG", "ada" if model else "KOSONG",
        )
        raise AIUnavailable("Model text atau kunci API belum dikonfigurasi")
    base_url = os.environ.get("AI_BASE_URL", "https://ai.sumopod.com/v1").rstrip("/")
    if not base_url.startswith("https://"):
        raise AIUnavailable("AI_BASE_URL harus memakai HTTPS")
    payload = {
        "model": model, "temperature": 0, "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": json.dumps(facts, ensure_ascii=False)},
        ],
    }
    request = Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=12) as response:
            data = json.load(response)
        content = data["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("AI response is not text")
        return json.loads(content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip())
    except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
        logger.warning("Panggilan AI text (JSON) gagal: %r", error)
        raise AIUnavailable("Permintaan AI gagal") from error


def generate_personal_note(profile, shade):
    """Optional wording; shade ranking is entirely in recommendation.py."""
    facts = {
        "skin_tone": profile.get("skin_tone"),
        "undertone": profile.get("undertone"),
        "lip_pigmentation": profile.get("lip_pigmentation"),
        "shade_name": shade["shade_name"],
        "color_family": shade["color_family"],
        "intensity": shade["intensity"],
        "finish": shade["finish"],
    }
    return _text_completion(
        "Write one short Indonesian sentence explaining a cosmetic shade suggestion "
        "using only supplied facts. Use tentative language. Do not invent scientific "
        "evidence, ratings, product performance, or health claims.",
        facts, max_tokens=120,
    )[:500]


def refine_shade_pick(role_label, candidates, profile, preference):
    """Bounded personalization for ONE recommendation role.

    `candidates` is recommendation.top_candidates()'s output for that role:
    a short list (already ranked, already scored by deterministic
    color-science math -- see services/recommendation.py). This function's
    ONLY job is to pick which of those already-valid candidates best fits
    qualitative details a numeric rule can't easily capture (the wearer's
    free-text visible_lip_condition, stated preference nuances). It cannot
    introduce a new shade_id, cannot invent or override a score, and if its
    response doesn't name one of the given candidates, the caller
    (recommendation.personalize) discards it and keeps the deterministic
    pick. This is the "Claude does optimization/personalization, not
    prediction from scratch" boundary the rest of this app also follows.

    Returns (shade_id, reason_text). Raises AIUnavailable if the API is
    unreachable/unconfigured or its answer fails validation.
    """
    facts = {
        "role": role_label,
        "skin_tone": profile.get("skin_tone"),
        "undertone": profile.get("undertone"),
        "lip_pigmentation": profile.get("lip_pigmentation"),
        "visible_lip_condition": profile.get("visible_lip_condition", ""),
        "stated_preference": preference,
        "candidates": [
            {
                "shade_id": c["shade_id"], "shade_name": c["shade_name"],
                "color_family": c["color_family"], "finish": c["finish"],
                "intensity": c["intensity"],
                "color_science_score": c.get("score"),
                "measured_contrast_L_star": (c.get("metrics") or {}).get("contrast"),
                "measured_hue_difference_degrees": (c.get("metrics") or {}).get("hue_diff"),
            }
            for c in candidates
        ],
    }
    result = _json_completion(
        "You personalize a lipstick shade pick for one wearer. You are given a "
        "SHORT LIST of candidate shades that have ALREADY been scored by a "
        "deterministic color-science calculation (facial-contrast and "
        "hue-harmony metrics) -- that scoring is final; do not re-derive or "
        "second-guess it with your own color theory. Your only job: pick the "
        "ONE shade_id from the given candidates whose qualitative details "
        "(visible lip condition, stated preference) best match this wearer, "
        "or return the candidate with the highest color_science_score if "
        "nothing else distinguishes them. You must choose a shade_id that is "
        "EXACTLY one of the given candidates -- never invent one, never "
        "return a shade not in the list. Return JSON only: "
        '{"shade_id": "...", "reason": "one short Indonesian sentence, no '
        'invented facts, no health or performance claims"}.',
        facts, max_tokens=150,
    )
    valid_ids = {c["shade_id"] for c in candidates}
    shade_id = result.get("shade_id")
    reason = result.get("reason")
    if shade_id not in valid_ids or not isinstance(reason, str) or not reason.strip():
        raise AIUnavailable("Hasil personalisasi AI tidak valid; gunakan urutan default")
    return shade_id, reason.strip()[:300]


def generate_opportunity_summary(opportunity):
    facts = {
        "target_shade": opportunity["target_shade_name"],
        "target_segment": opportunity["target_segment"].replace("_", " "),
        "preferred_finish": opportunity["preferred_finish"],
        "positive_interest_count": opportunity["demo_interest"],
        "new_local_requests": opportunity["local_requests"],
        "related_wear_issue_count": opportunity["related_issues"],
    }
    return _text_completion(
        "Write two short Indonesian sentences for a cosmetics R&D team, as a production "
        "system reporting on real consumer signal (not a prototype or test environment). "
        "Explain the provided numbers as one integrated view of consumer interest and "
        "suggest a lab review. Never use the words 'demo', 'pilot', 'sintetis', 'simulasi', "
        "'contoh', or any other wording that implies the data is a placeholder or a test "
        "run. Do not claim statistical significance, future trend prediction, product "
        "safety, clinical evidence, or a validated formula. Do not invent numbers.",
        facts,
    )


def generate_formula_rationale(brief):
    """Narrate the ADJUSTMENT DIRECTION from a fixed baseline formula only.

    `brief` must be a build_formula_brief() result with needs_target_color
    and needs_reference both False -- callers (research/views.py) must check
    those flags themselves and skip this call otherwise; there is no valid
    baseline composition to narrate an adjustment from in either case, and
    calling this on such a brief would raise a KeyError on brief["baseline"].

    Mirrors refine_shade_pick's boundary: the baseline composition
    percentages in `brief["baseline_composition"]` are ALREADY FIXED,
    deterministic numbers (nearest-neighbour match in services/formula_lab.py
    against base_formula_reference.csv). This function may only describe,
    in words, which direction to nudge them -- the prompt explicitly forbids
    new percentages, a full recipe, or ingredient safety claims.
    """
    opportunity = brief["opportunity"]
    baseline = brief["baseline"]
    facts = {
        "target_shade_concept": opportunity["target_shade_name"],
        "target_family": opportunity["family"],
        "target_finish": opportunity["preferred_finish"],
        "positive_interest_count": opportunity["demo_interest"],
        "new_local_requests": opportunity["local_requests"],
        "related_wear_issue_count": opportunity["related_issues"],
        "top_reported_issue": brief["top_issue"],
        "baseline_reference_shade_name": baseline["shade_name"],
        "baseline_reference_color_family": baseline["color_family"],
        "baseline_reference_finish": baseline["finish"],
        "baseline_color_distance_from_target_dE76": baseline["distance"],
        "baseline_composition_percent": brief["baseline_composition"],
    }
    return _text_completion(
        "Write two short Indonesian sentences for a lipstick formulator, explaining "
        "the ADJUSTMENT DIRECTION from the given baseline reference formula toward "
        "the target shade concept. The baseline_composition_percent values are the "
        "ALREADY-FIXED starting point (a nearest-color-match lookup, not your "
        "choice) -- you may describe qualitatively raising or lowering one "
        "component (e.g. 'sedikit lebih banyak pigmen', 'kurangi wax') based on "
        "target_finish / top_reported_issue, but you must NEVER output a new "
        "percentage, a full recipe, or ingredient safety claims. Make clear a "
        "formulator and laboratory must validate any change, and that this "
        "baseline is reference data awaiting lab validation, not a finished formula. "
        "Never use the words 'demo', 'pilot', 'sintetis', 'simulasi', 'contoh', or any "
        "other wording that implies the data is a placeholder or a test run. "
        "Do not invent study results or numbers not supplied.",
        facts,
    )