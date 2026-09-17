"""Small, transparent aggregations over demo CSV and feedback saved by this app."""

from collections import Counter

from consumer.models import Feedback
from services.data import read_demo_csv, shades


POSITIVE_INTEREST = {"love_it", "like_it"}
ISSUE_VALUES = {"too_pale", "too_dark", "too_dry", "too_sticky", "too_thick", "too_matte", "too_glossy"}


def _family(value):
    return "mauve" if value == "mauve_rose" else value


def _tone_group(value):
    if value in {"light", "light_medium"}:
        return "light"
    if value in {"medium", "tan"}:
        return "medium_tan"
    return value


def _undertone_group(value):
    return "warm_olive" if value in {"warm", "olive", "warm_olive"} else value


def signals():
    catalog = {row["shade_id"]: row for row in shades()}
    profiles = {row["profile_id"]: row for row in read_demo_csv("demo_consumer_profiles.csv")}
    rows = []
    for row in read_demo_csv("demo_feedback.csv"):
        profile = profiles.get(row["profile_id"], {})
        shade = catalog.get(row["shade_id"], {})
        rows.append({**row, "source": "demo", "skin_tone": profile.get("skin_tone", ""),
                     "undertone": profile.get("undertone", ""),
                     "region": profile.get("region", ""),
                     "shade_name": shade.get("shade_name", row["shade_id"]),
                     "color_family": shade.get("color_family", ""),
                     "desired_color_family": "", "desired_finish": ""})
    for entry in Feedback.objects.all():
        shade = catalog.get(entry.shade_id, {})
        rows.append({
            "source": "local", "shade_id": entry.shade_id,
            "shade_name": entry.shade_name, "color_family": shade.get("color_family", ""),
            "skin_tone": entry.skin_tone, "undertone": entry.undertone,
            "region": entry.region, "feedback_type": entry.feedback_type,
            "color_response": entry.color_response,
            "texture_response": entry.texture_response,
            "finish_response": entry.finish_response,
            "rating": str(entry.rating or ""), "comment": entry.comment,
            "desired_color_family": entry.desired_color_family,
            "desired_finish": entry.desired_finish,
        })
    return rows


def affinity(shade_id, profile):
    """Report count and denominator, never a confidence/accuracy percentage."""
    interest = [row for row in signals() if row["shade_id"] == shade_id
                and row["feedback_type"] == Feedback.INTEREST]
    cohort = [row for row in interest
              if _tone_group(row["skin_tone"]) == _tone_group(profile.get("skin_tone"))
              and _undertone_group(row["undertone"]) == _undertone_group(profile.get("undertone"))]
    selected = cohort if cohort else interest
    return {
        "positive": sum(row["color_response"] in POSITIVE_INTEREST for row in selected),
        "sample": len(selected),
        "cohort": bool(cohort),
        "demo_sample": sum(row["source"] == "demo" for row in selected),
        "local_sample": sum(row["source"] == "local" for row in selected),
    }


def community_spectrum(profile):
    interest = [row for row in signals()
                if row["feedback_type"] == Feedback.INTEREST
                and row["color_response"] in POSITIVE_INTEREST
                and _tone_group(row["skin_tone"]) == _tone_group(profile.get("skin_tone"))
                and _undertone_group(row["undertone"]) == _undertone_group(profile.get("undertone"))]
    counts = Counter(row["color_family"] for row in interest if row["color_family"])
    maximum = max(counts.values(), default=1)
    return [{"family": family, "count": count, "width": round(count / maximum * 100)}
            for family, count in counts.most_common()]


def family_hex(family):
    """A representative real hex for a color family, straight from the shade
    catalog -- never an invented/guessed color. Used so a color family's
    accent dot/line on a chart is actually that family's own real hue,
    instead of an arbitrary repeating palette."""
    for row in shades():
        if row["color_family"] == family:
            return row["hex"]
    return None


def _trend_chart(pairs, width=520, height=170, pad_x=10, pad_top=16, pad_bottom=38):
    """SVG coordinates for a ranked chart from real (label, value) pairs.

    This ranks real counts highest-to-lowest -- it is NOT a time-series
    trend. Nothing in this app's data currently tracks a submission date
    for these aggregates, so this never pretends to plot change over time
    the way the reference mockups' "last 14 days" chart does.
    """
    pairs = [p for p in pairs if p[1]]
    if not pairs:
        return {"markers": [], "points": "", "area": "", "width": width, "height": height, "baseline": height - pad_bottom}
    values = [v for _, v in pairs]
    max_value = max(values) or 1
    n = len(pairs)
    baseline = height - pad_bottom
    top = pad_top
    step = (width - 2 * pad_x) / (n - 1) if n > 1 else 0
    markers = []
    for i, (label, value) in enumerate(pairs):
        x = round(pad_x + step * i, 1)
        y = round(baseline - (value / max_value) * (baseline - top), 1)
        markers.append({"x": x, "y": y, "label": label, "value": value, "hex": family_hex(label)})
    points = " ".join(f"{m['x']},{m['y']}" for m in markers)
    area = f"{markers[0]['x']},{baseline} " + points + f" {markers[-1]['x']},{baseline}"
    return {"markers": markers, "points": points, "area": area, "width": width, "height": height, "baseline": baseline}


def overview():
    rows = signals()
    demo = [row for row in rows if row["source"] == "demo"]
    local = [row for row in rows if row["source"] == "local"]
    wear_ratings = [int(row["rating"]) for row in rows
                    if row["feedback_type"] == Feedback.WEAR and row["rating"].isdigit()]
    families = Counter(row["color_family"] for row in rows
                       if row["feedback_type"] == Feedback.INTEREST
                       and row["color_response"] in POSITIVE_INTEREST
                       and row["color_family"])
    requests = Counter(row["desired_color_family"] for row in local if row["desired_color_family"])
    family_rows = families.most_common(6)
    total_positive = sum(count for _, count in family_rows) or 1
    shade_family_rows = [
        {"family": family, "count": count, "hex": family_hex(family),
         "share": round(count / total_positive * 100)}
        for family, count in family_rows
    ]
    request_rows = requests.most_common(5)
    max_request = max((count for _, count in request_rows), default=1) or 1
    local_request_rows = [
        {"family": family, "count": count, "hex": family_hex(family),
         "width": round(count / max_request * 100)}
        for family, count in request_rows
    ]
    return {
        "demo_feedback_count": len(demo),
        "local_feedback_count": len(local),
        "interest_count": sum(row["feedback_type"] == Feedback.INTEREST for row in rows),
        "wear_count": sum(row["feedback_type"] == Feedback.WEAR for row in rows),
        "average_wear_rating": round(sum(wear_ratings) / len(wear_ratings), 2) if wear_ratings else None,
        "shade_families": family_rows,
        "shade_family_rows": shade_family_rows,
        "family_trend": _trend_chart(family_rows),
        "local_requests": request_rows,
        "local_request_rows": local_request_rows,
        "opportunity_count": len(read_demo_csv("opportunities_v2.csv")),
    }


def sample_comment(family):
    """One real consumer comment tied to a color family, or None.

    Picks the most recent local comment first (real users, not the demo
    CSV), falling back to a demo comment. Never fabricated -- if nobody
    actually wrote a comment tied to this family, this returns None and the
    template must say so rather than inventing a quote.
    """
    rows = [row for row in signals() if row["comment"]
            and (row["color_family"] == family or row["desired_color_family"] == family)]
    local = [row for row in rows if row["source"] == "local"]
    if local:
        return local[-1]
    return rows[0] if rows else None


LEVEL_LABELS = {"high": "tinggi", "medium": "sedang", "low": "rendah"}


def opportunities():
    rows = signals()
    catalog = {row["shade_name"]: row for row in shades()}
    result = []
    for item in read_demo_csv("opportunities_v2.csv"):
        family = _family(item["target_family"])
        concept = catalog.get(item["target_shade_name"], {})
        demo_interest = sum(
            row["source"] == "demo" and row["shade_id"] == concept.get("shade_id")
            and row["feedback_type"] == Feedback.INTEREST
            and row["color_response"] in POSITIVE_INTEREST
            for row in rows
        )
        local_requests = sum(
            row["source"] == "local" and row["desired_color_family"] == family
            and (not row["desired_finish"] or row["desired_finish"] == item["preferred_finish"])
            for row in rows
        )
        related_issues = sum(
            row["feedback_type"] == Feedback.WEAR
            and row["color_family"] == family
            and any(row[field] in ISSUE_VALUES for field in
                    ("color_response", "texture_response", "finish_response"))
            for row in rows
        )
        result.append({**item, "family": family, "concept_id": concept.get("shade_id", ""),
                       "demo_interest": demo_interest, "local_requests": local_requests,
                       "related_issues": related_issues, "sample_comment": sample_comment(family),
                       "target_segment_label": item["target_segment"].replace("_", " "),
                       "demand_signal_label": LEVEL_LABELS.get(item["demand_signal"], item["demand_signal"]),
                       "portfolio_match_label": LEVEL_LABELS.get(item["portfolio_match"], item["portfolio_match"])})
    return result


def evidence(opportunity_id=None):
    all_opportunities = opportunities()
    selected = next((item for item in all_opportunities if item["opportunity_id"] == opportunity_id), None)
    rows = signals()
    if selected:
        rows = [row for row in rows if row["color_family"] == selected["family"]
                or row["desired_color_family"] == selected["family"]]
    demo_issues = Counter()
    local_issues = Counter()
    for row in rows:
        target = demo_issues if row["source"] == "demo" else local_issues
        if row["feedback_type"] != Feedback.WEAR:
            continue
        for field in ("color_response", "texture_response", "finish_response"):
            value = row.get(field, "")
            if value in ISSUE_VALUES:
                target[value.replace("_", " ")] += 1
    demo_comments = [row for row in rows if row["source"] == "demo" and row["comment"]][:6]
    local_comments = [row for row in reversed(rows) if row["source"] == "local" and row["comment"]][:10]
    return {
        "selected_opportunity": selected,
        "opportunities": all_opportunities,
        "demo_issues": demo_issues.most_common(6),
        "local_issues": local_issues.most_common(6),
        "demo_comments": demo_comments,
        "local_comments": local_comments,
        "all_comments": local_comments + demo_comments,
        "demo_issue_total": sum(demo_issues.values()),
        "local_issue_total": sum(local_issues.values()),
    }