import csv
from functools import lru_cache
from pathlib import Path

from django.conf import settings


DATA_DIR = Path(settings.BASE_DIR) / "data" / "formusense_demo"


@lru_cache(maxsize=8)
def read_demo_csv(filename):
    allowed = {
        "shade_catalog.csv", "demo_feedback.csv", "opportunities.csv",
        "formula_draft_demo.csv", "demo_consumer_profiles.csv",
    }
    if filename not in allowed:
        raise ValueError("Dataset tidak dikenal")
    with (DATA_DIR / filename).open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def shades(available_only=False):
    rows = read_demo_csv("shade_catalog.csv")
    if available_only:
        return [row for row in rows if row["portfolio_status"] in {"existing", "limited_match"}]
    return rows


def shade_by_id(shade_id, available_only=False):
    from services.team_data import catalog_shade_by_id

    team_shade = catalog_shade_by_id(shade_id)
    if team_shade:
        return team_shade
    return next((row for row in shades(available_only) if row["shade_id"] == shade_id), None)
