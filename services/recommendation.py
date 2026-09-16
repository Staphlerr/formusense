from services.data import shades


def _score(shade, profile, preference, role):
    score = 0
    undertone = profile.get("undertone", "neutral")
    fit = shade["undertone_fit"]
    if undertone == fit:
        score += 5
    elif undertone in fit or fit in {"neutral", "warm_olive"} and undertone in {"warm", "olive"}:
        score += 3
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


def recommend(profile, preference):
    """Return three distinct, currently available demo shades. No AI call is needed."""
    pool = shades(available_only=True)
    results = []
    for role, label in [
        ("daily", "Daily Natural"),
        ("energized", "Energized Vibe"),
        ("bold", "Bold Statement"),
    ]:
        remaining = [row for row in pool if row["shade_id"] not in {x["shade_id"] for x in results}]
        picked = max(remaining, key=lambda row: _score(row, profile, preference, role))
        results.append({**picked, "role": role, "role_label": label,
                        "reason": _reason(picked, profile, preference)})
    return results


def _reason(shade, profile, preference):
    parts = [f"Warna {shade['color_family']} dengan hasil {shade['finish']}."]
    if shade["undertone_fit"] == profile.get("undertone"):
        parts.append("Arah warnanya sesuai dengan undertone yang dipilih.")
    if shade["finish"] == preference.get("finish"):
        parts.append("Hasil akhirnya sesuai preferensimu.")
    return " ".join(parts)
