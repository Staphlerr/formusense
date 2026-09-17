"""Generate a review brief from an opportunity, benchmarked against the
closest EXISTING reference formula in measured CIELAB color space -- never
an invented recipe.

This replaces the previous version of this module, which produced
`pigment_direction` / `base_direction` as 100% hardcoded if/elif text keyed
only on `family` / `preferred_finish`, with zero connection to any actual
formula data. That matched nothing in `data/formusense_demo/*.csv` and
skipped the base-formula-benchmarking step the original hackathon plan
required.

The core idea, matching that plan's explicit requirement ("Formula draft
berangkat dari base formula... Jika belum ada formula dasar valid, tampilkan
NEEDS_REFERENCE alih-alih mengarang takaran."): a formula draft must start
from a real, existing formula, not be conjured from nothing. This module
finds the nearest candidate by real measured color distance (CIELAB dE76)
and refuses (NEEDS_REFERENCE) rather than guess when nothing is close enough.

Two things this module is explicitly NOT allowed to do:
1. Invent a target color. `build_formula_brief` requires the opportunity to
   carry a `target_hex` (a swatch a human on the team picked) -- if it's
   missing, the brief says so (`needs_target_color`) instead of guessing one.
2. Invent a new composition. The nearest reference formula's percentages are
   reported as-is; `services.ai_client.generate_formula_rationale` is only
   allowed to describe the ADJUSTMENT DIRECTION from that fixed baseline, in
   words -- never output new percentages (enforced in that function's
   prompt, not here).

Data provenance note (confirmed with the team, 2026-09-17): the 500-row
`base_formula_reference_v2.csv` this module reads is a REFERENCE/GENERATED
dataset for the prototype, not formulas a pharmacy/formulator team member has
physically reviewed. Every UI surface that shows a "baseline" from this file
must keep saying so -- "requires lab validation", not "validated formula".
"""

from collections import Counter
import csv
from functools import lru_cache
from pathlib import Path

from django.conf import settings

from services.analytics import opportunities, signals
from services.color_science import lab_from_hex


DATA_DIR = Path(settings.BASE_DIR) / "data" / "formusense_demo"

# How close (Euclidean CIELAB distance, dE76) an existing reference formula's
# color must be to the opportunity's target color before it counts as a
# usable starting point. There is no universal cutoff for "close enough to
# adjust from" the way there is for "perceptually identical" (~2.3 dE) --
# this is OUR chosen prototype threshold: loose enough to find a
# same-family starting point, tight enough to refuse a wrong-color guess.
# Say so if asked; tune against real formulator judgement, not this comment.
MAX_REFERENCE_DISTANCE = 20.0

VALIDATION_STEPS = [
    "Periksa identitas, izin, dan batas pemakaian setiap bahan",
    "Buat beberapa batch percobaan dengan variasi rasio pigmen",
    "Uji drawdown warna dan payoff pada beberapa warna bibir",
    "Uji stabilitas, tekstur, dan kenyamanan pemakaian",
    "Lakukan uji kesukaan konsumen sebelum keputusan produk",
]

COMPOSITION_FIELDS = [
    "wax_pct", "emollient_oil_pct", "mattifying_agent_pct",
    "film_former_pct", "pigment_pct", "additives_pct",
]


@lru_cache(maxsize=1)
def base_formulas():
    """500 reference formulas: measured Lab color + full composition (each
    row's composition fields sum to 100%). See the data-provenance note in
    this module's docstring -- this is prototype reference data, not a
    formulator-reviewed recipe book.
    """
    path = DATA_DIR / "base_formula_reference_v2.csv"
    with path.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    for row in rows:
        row["lab"] = (float(row["L_star"]), float(row["a_star"]), float(row["b_star"]))
        for field in COMPOSITION_FIELDS:
            row[field] = float(row[field])
    return rows


def _lab_distance(lab_a, lab_b):
    return sum((x - y) ** 2 for x, y in zip(lab_a, lab_b)) ** 0.5


def nearest_base_formulas(target_lab, family=None, finish=None, n=3):
    """Rank reference formulas by measured color distance to target_lab.

    `family` / `finish` only break near-ties in favor of a same-family or
    same-finish reference when the color match is comparable -- they never
    override the Lab-distance ranking itself (a closer wrong-family color
    still loses to color distance alone if the gap is large).
    """
    def sort_key(row):
        bonus = 0.0
        if family and row["color_family"].lower() == family.lower():
            bonus -= 2.0
        if finish and row["finish"].lower() == finish.lower():
            bonus -= 1.0
        return _lab_distance(target_lab, row["lab"]) + bonus

    ranked = sorted(base_formulas(), key=sort_key)
    return [
        {**row, "distance": round(_lab_distance(target_lab, row["lab"]), 2)}
        for row in ranked[:n]
    ]


def _composition_summary(formula):
    return {field: formula[field] for field in COMPOSITION_FIELDS}


def build_formula_brief(opportunity_id):
    """Deterministic computation only -- no AI call happens in this module.

    Returns {"brief": {...}} where brief always carries `needs_target_color`
    and `needs_reference` booleans. The caller (research/views.py) must
    check both before ever calling generate_formula_rationale: if either is
    true, there is no valid baseline to narrate an adjustment from.
    """
    item = next((row for row in opportunities() if row["opportunity_id"] == opportunity_id), None)
    if item is None:
        raise ValueError("Peluang tidak ditemukan")

    related = [row for row in signals() if row["color_family"] == item["family"]
               or row["desired_color_family"] == item["family"]]
    issues = Counter()
    for row in related:
        if row["feedback_type"] != "wear_feedback":
            continue
        for field in ("color_response", "texture_response", "finish_response"):
            value = row[field]
            if value.startswith("too_"):
                issues[value] += 1
    top_issue = issues.most_common(1)[0][0].replace("_", " ") if issues else None
    common = {
        "opportunity": item,
        "top_issue": top_issue,
        "issues_sample": sum(issues.values()),
        "validation_steps": VALIDATION_STEPS,
    }

    target_hex = (item.get("target_hex") or "").strip()
    if not target_hex:
        # No target swatch chosen yet for this concept -- refuse to guess one.
        return {"brief": {
            **common,
            "needs_target_color": True,
            "needs_reference": False,
            "nearest_formulas": [],
            "baseline": None,
            "baseline_composition": None,
        }}

    target_lab = lab_from_hex(target_hex)
    candidates = nearest_base_formulas(
        target_lab, family=item["family"], finish=item["preferred_finish"], n=3
    )
    nearest = candidates[0]
    needs_reference = nearest["distance"] > MAX_REFERENCE_DISTANCE

    return {"brief": {
        **common,
        "target_hex": target_hex,
        "target_lab": tuple(round(v, 1) for v in target_lab),
        "needs_target_color": False,
        "needs_reference": needs_reference,
        "nearest_formulas": candidates,
        "baseline": None if needs_reference else nearest,
        "baseline_composition": None if needs_reference else _composition_summary(nearest),
    }}