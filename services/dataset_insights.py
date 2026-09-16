"""Source-labelled demo insights; external datasets never become preference evidence."""

import csv
import json
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from django.conf import settings


ROOT = Path(settings.BASE_DIR) / "data"
HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}\Z")


def _rows(path):
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


@lru_cache(maxsize=1)
def public_lipstick_swatches():
    """Public product swatches only, not validated suitability or stock status."""
    path = ROOT / "external_sources" / "capstone_colors_original" / "processed" / "products_app.csv"
    result = []
    for row in _rows(path):
        color = (row.get("hex_colors") or "").strip()
        if row.get("category") != "lipstick" or not HEX_COLOR.fullmatch(color):
            continue
        result.append({
            "brand": row["brand"].strip(),
            "product": row["product"].strip(),
            "shade": row["shade"].strip(),
            "hex": color.upper(),
        })
    return result


def _rgb(color):
    return tuple(int(color[index:index + 2], 16) for index in (1, 3, 5))


def public_swatches_near(picks):
    """Give two color-near source examples per demo pick; no product matching claim."""
    used = set()
    examples = []
    for pick in picks:
        target = _rgb(pick["hex"])
        candidates = sorted(
            enumerate(public_lipstick_swatches()),
            key=lambda item: sum((a - b) ** 2 for a, b in zip(target, _rgb(item[1]["hex"]))),
        )
        for index, row in candidates:
            if index in used:
                continue
            used.add(index)
            examples.append({**row, "near_demo_shade": pick["shade_name"]})
            break
    return examples


@lru_cache(maxsize=1)
def dataset_insights():
    """Aggregate standalone datasets without joining their incompatible IDs."""
    demo = ROOT / "formusense_demo"
    shade_families = {
        row["shade_id"]: row["color_family"]
        for row in _rows(demo / "shade_data.csv")
    }
    hedonic = _rows(demo / "hedonic_data.csv")
    family_scores = defaultdict(list)
    for row in hedonic:
        family = shade_families.get(row["shade_id"])
        if family:
            family_scores[family].append(int(row["hedonic_score"]))
    by_family = sorted(
        (
            {"family": family, "count": len(scores), "mean": round(sum(scores) / len(scores), 2)}
            for family, scores in family_scores.items()
        ),
        key=lambda item: (-item["mean"], item["family"]),
    )
    foundation = ROOT / "external_sources" / "the_pudding_makeup_shades" / "shades.csv"
    shampoo = ROOT / "external_sources" / "nature_shampoo_formulation" / "LiquidFormulationsDataset_2023.json"
    formula_outputs = _rows(demo / "formula_outputs.csv")
    with shampoo.open(encoding="utf-8") as source:
        shampoo_count = len(json.load(source))
    return {
        "public_lipstick_count": len(public_lipstick_swatches()),
        "synthetic_hedonic_count": len(hedonic),
        "synthetic_shade_count": len(shade_families),
        "synthetic_formula_count": len(_rows(demo / "formulation_data.csv")),
        "synthetic_formula_output_count": len(formula_outputs),
        "synthetic_mean_hardness": round(
            sum(float(row["hardness"]) for row in formula_outputs) / len(formula_outputs), 2
        ),
        "synthetic_mean_payoff": round(
            sum(float(row["payoff"]) for row in formula_outputs) / len(formula_outputs), 2
        ),
        "foundation_reference_count": len(_rows(foundation)),
        "shampoo_reference_count": shampoo_count,
        "hedonic_by_family": by_family,
    }
