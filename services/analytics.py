"""Small, transparent aggregations over demo CSV and feedback saved by this app."""

from collections import Counter

from consumer.models import Feedback
from services.data import read_demo_csv, shades
from services.team_data import catalog_shades, shade_evidence


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
    catalog = {row["shade_id"]: row for row in [*shades(), *catalog_shades()]}
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
    team_shade = next((row for row in catalog_shades() if row["shade_id"] == shade_id), None)
    if team_shade:
        historical = shade_evidence(team_shade, profile)
        local = [row for row in signals() if row["source"] == "local"
                 and row["shade_id"] == shade_id and row["feedback_type"] == Feedback.INTEREST]
        local_cohort = [row for row in local
                        if _tone_group(row["skin_tone"]) == _tone_group(profile.get("skin_tone"))
                        and _undertone_group(row["undertone"]) == _undertone_group(profile.get("undertone"))]
        selected_local = local_cohort if local_cohort else local
        return {
            "positive": historical["review_positive"] + sum(row["color_response"] in POSITIVE_INTEREST
                                                         for row in selected_local),
            "sample": historical["review_sample"] + len(selected_local),
            "cohort": historical["review_cohort"] != "semua profil" or bool(local_cohort),
            "historical_sample": historical["review_sample"],
            "demo_sample": 0, "local_sample": len(selected_local),
        }
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
        "historical_sample": 0,
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
    return {
        "demo_feedback_count": len(demo),
        "local_feedback_count": len(local),
        "interest_count": sum(row["feedback_type"] == Feedback.INTEREST for row in rows),
        "wear_count": sum(row["feedback_type"] == Feedback.WEAR for row in rows),
        "average_wear_rating": round(sum(wear_ratings) / len(wear_ratings), 2) if wear_ratings else None,
        "shade_families": families.most_common(6),
        "local_requests": requests.most_common(5),
        "opportunity_count": len(read_demo_csv("opportunities.csv")),
    }


def opportunities():
    rows = signals()
    catalog = {row["shade_name"]: row for row in shades()}
    result = []
    for item in read_demo_csv("opportunities.csv"):
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
                       "related_issues": related_issues})
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
    return {
        "selected_opportunity": selected,
        "opportunities": all_opportunities,
        "demo_issues": demo_issues.most_common(6),
        "local_issues": local_issues.most_common(6),
        "demo_comments": [row for row in rows if row["source"] == "demo" and row["comment"]][:6],
        "local_comments": [row for row in reversed(rows) if row["source"] == "local" and row["comment"]][:10],
    }
