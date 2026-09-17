"""Adapters for the five team-supplied CSVs.

These files have no verified Paragon provenance. They are demo evidence, not
measurements of Paragon's real portfolio or validated laboratory outcomes.
"""

import csv
import re
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

from django.conf import settings


ROOT = Path(settings.BASE_DIR) / "data"
FILES = {
    "catalog": "ALL DATASET - Shade Catalog.csv",
    "hedonic": "ALL DATASET - Hedonic Customer Data.csv",
    "feedback": "ALL DATASET - Feedback.csv",
    "formula": "ALL DATASET - Base Formula.csv",
    "gap": "ALL DATASET - Gap Comparison.csv",
}
FORMULA_PARTS = (
    "wax_pct", "emollient_oil_pct", "mattifying_agent_pct",
    "film_former_pct", "pigment_pct", "additives_pct",
)


@lru_cache(maxsize=5)
def team_rows(kind):
    if kind not in FILES:
        raise ValueError("Dataset tim tidak dikenal")
    with (ROOT / FILES[kind]).open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


@lru_cache(maxsize=1)
def catalog_shades():
    intensity = {"soft": "light", "medium": "medium", "deep": "bold"}
    return [{
        "shade_id": row["shade_id"],
        "shade_name": row["name"],
        "brand": row["Brand"],
        "color_family": row["color_family"].lower(),
        "hex": row["hex"].upper(),
        "undertone_fit": row["undertone_fit"].lower(),
        "intensity": intensity[row["intensity"].lower()],
        "finish": row["finish"].lower(),
        "portfolio_status": "team_catalog",
    } for row in team_rows("catalog")]


def catalog_shade_by_id(shade_id):
    return next((row for row in catalog_shades() if row["shade_id"] == shade_id), None)


def _tone_group(value):
    value = (value or "").lower().replace("_", " ")
    if value in {"fair", "light", "light medium"}:
        return "light"
    if value in {"medium", "tan"}:
        return "medium_tan"
    return value


def _cohort(rows, profile):
    tone = _tone_group(profile.get("skin_tone"))
    undertone = (profile.get("undertone") or "").lower()
    exact = [row for row in rows if _tone_group(row.get("skin_tone") or row.get("Skintone")) == tone
             and (row.get("undertone") or row.get("Undertone", "")).lower() == undertone]
    if len(exact) >= 3:
        return exact, "warna kulit dan undertone serupa"
    same_undertone = [row for row in rows
                      if (row.get("undertone") or row.get("Undertone", "")).lower() == undertone]
    if len(same_undertone) >= 3:
        return same_undertone, "undertone serupa"
    return rows, "semua profil"


def shade_evidence(shade, profile):
    """Separate synthetic hedonic liking from historical-style review appeal."""
    hedonic = [row for row in team_rows("hedonic") if row["shade"] == shade["shade_name"]]
    h_selected, h_cohort = _cohort(hedonic, profile)
    h_scores = [int(row["hedonic_scale"]) for row in h_selected]
    reviews = [row for row in team_rows("feedback") if row["shade_id"] == shade["shade_id"]]
    r_selected, r_cohort = _cohort(reviews, profile)
    positives = sum(row["appealing"] in {"Love it", "Like it"} for row in r_selected)
    return {
        "hedonic_mean": round(sum(h_scores) / len(h_scores), 2) if h_scores else None,
        "hedonic_sample": len(h_scores), "hedonic_cohort": h_cohort,
        "review_positive": positives, "review_sample": len(r_selected),
        "review_cohort": r_cohort,
    }


def hedonic_spectrum(profile):
    catalog_by_name = {row["shade_name"]: row for row in catalog_shades()}
    rows, cohort = _cohort(team_rows("hedonic"), profile)
    scores = defaultdict(list)
    for row in rows:
        shade = catalog_by_name.get(row["shade"])
        if shade:
            scores[shade["color_family"]].append(int(row["hedonic_scale"]))
    return {
        "cohort": cohort,
        "families": sorted(({
            "family": family, "mean": round(sum(values) / len(values), 2),
            "sample": len(values), "width": round(sum(values) / len(values) / 9 * 100),
        } for family, values in scores.items()), key=lambda item: (-item["mean"], item["family"])),
    }


def feedback_summary():
    rows = team_rows("feedback")
    ratings = [int(row["overall_rating"]) for row in rows if row["overall_rating"].isdigit()]
    return {
        "count": len(rows),
        "mean_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
        "appeal": Counter(row["appealing"] for row in rows).most_common(),
        "texture_issues": Counter(row["texture"] for row in rows
                                  if row["texture"].startswith("Too ")).most_common(),
        "finish_issues": Counter(row["finish"] for row in rows
                                 if row["finish"].startswith("Too ")).most_common(),
        "color_issues": Counter(row["color"] for row in rows
                                if row["color"].startswith("Too ")).most_common(),
    }


def _existing_catalog_match(gap):
    match = re.match(r"^Shade \d+ - (.+) \((.+)\)$", gap["existing_shade"])
    if not match:
        return False
    name, brand = match.groups()
    return any(shade["shade_name"].casefold() == name.casefold()
               and shade["brand"].casefold() == brand.casefold()
               for shade in catalog_shades())


def gap_candidates():
    return [{**row, "index": index, "catalog_match": _existing_catalog_match(row)}
            for index, row in enumerate(team_rows("gap"))]


def team_dataset_summary():
    gaps = gap_candidates()
    return {
        "catalog_count": len(catalog_shades()),
        "hedonic_count": len(team_rows("hedonic")),
        "feedback_count": len(team_rows("feedback")),
        "formula_count": len(team_rows("formula")),
        "gap_count": len(gaps),
        "gap_catalog_matches": sum(row["catalog_match"] for row in gaps),
        "gap_types": Counter(row["gap_type"] for row in gaps).most_common(),
    }


def finish_coverage():
    """Compare stated finish preferences to finishes present in the demo catalog."""
    from consumer.models import Feedback

    catalog_counts = Counter(row["finish"] for row in catalog_shades())
    historic_requests = Counter()
    for row in team_rows("hedonic"):
        match = re.search(r"(?:^|\|)\s*Finish:\s*([^|]+)", row["preference"], flags=re.I)
        if match:
            historic_requests[match.group(1).strip().lower()] += 1
    local_requests = Counter(
        row.lower() for row in Feedback.objects.exclude(desired_finish="")
        .values_list("desired_finish", flat=True)
    )
    names = set(catalog_counts) | set(historic_requests) | set(local_requests)
    return sorted(({
        "finish": name,
        "catalog_count": catalog_counts[name],
        "historic_requests": historic_requests[name],
        "local_requests": local_requests[name],
        "missing_in_demo": catalog_counts[name] == 0,
    } for name in names), key=lambda item: (not item["missing_in_demo"],
                                            -item["historic_requests"], item["finish"]))


def _extract_number(pattern, text):
    match = re.search(pattern, text, flags=re.I)
    return float(match.group(1)) if match else None


def _desired_finish(attributes):
    match = re.search(r"(?:^|\|)\s*([A-Za-z ]+?) Finish", attributes)
    return match.group(1).strip().lower() if match else None


def build_gap_formula_brief(index):
    """Nearest-reference composition for a gap; no trained performance predictor."""
    gaps = gap_candidates()
    if not 0 <= index < len(gaps):
        raise ValueError("Kandidat gap tidak ditemukan")
    gap = gaps[index]
    attributes = gap["desired_attributes"]
    target_finish = _desired_finish(attributes)
    target_l = _extract_number(r"Target L\*\s*\(([\d.]+)\)", attributes)
    target_pigment = _extract_number(r"Pigment\s*([\d.]+)%", attributes)
    target_wax = _extract_number(r"Wax\s*\(([\d.]+)%\)", attributes)
    family = gap["color_family"].lower()
    formulas = team_rows("formula")

    def distance(row):
        return (
            (0 if row["color_family"].lower() == family else 8)
            + (0 if target_finish is None or row["finish"].lower() == target_finish else 6)
            + (abs(float(row["L_star"]) - target_l) / 4 if target_l is not None else 0)
            + (abs(float(row["pigment_pct"]) - target_pigment) / 2 if target_pigment is not None else 0)
            + (abs(float(row["wax_pct"]) - target_wax) / 2 if target_wax is not None else 0)
        )

    nearest = sorted(formulas, key=distance)[:3]
    weights = [1 / (1 + distance(row)) for row in nearest]
    total_weight = sum(weights)
    amounts = {part: round(sum(float(row[part]) * weight for row, weight in zip(nearest, weights))
                           / total_weight, 2) for part in FORMULA_PARTS[:-1]}
    amounts[FORMULA_PARTS[-1]] = round(100 - sum(amounts.values()), 2)
    return {
        "gap": gap,
        "target_finish": target_finish,
        "target_finish_in_base": target_finish in {row["finish"].lower() for row in formulas},
        "target_l": target_l,
        "target_pigment": target_pigment,
        "target_wax": target_wax,
        "parts": amounts,
        "references": [{"shade_name": row["shade_name"], "finish": row["finish"],
                        "family": row["color_family"], "distance": round(distance(row), 2)}
                       for row in nearest],
        "total": round(sum(amounts.values()), 2),
    }
