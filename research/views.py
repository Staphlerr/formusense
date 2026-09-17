from django.http import Http404
from django.shortcuts import render

from accounts.access import research_required
from services.ai_client import AIUnavailable, generate_formula_rationale, generate_opportunity_summary
from services.analytics import evidence as evidence_data
from services.analytics import overview as overview_data
from services.analytics import opportunities as opportunity_data
from services.formula_lab import build_formula_brief
from services.dataset_insights import dataset_insights
from services.team_data import (
    build_gap_formula_brief, feedback_summary, finish_coverage,
    gap_candidates, team_dataset_summary,
)


@research_required
def overview(request):
    data = overview_data()
    shade_families = data.get("shade_families", [])
    local_requests = data.get("local_requests", [])
    return render(request, "research/overview.html", {
        **data, "datasets": dataset_insights(),
        "team": team_dataset_summary(), "team_feedback": feedback_summary(),
        "max_family_count": max((count for _, count in shade_families), default=0),
        "max_request_count": max((count for _, count in local_requests), default=0),
    })


@research_required
def unmet_demand(request):
    opportunities = opportunity_data()
    context = {"opportunities": opportunities, "team": team_dataset_summary(),
               "gap_candidates": gap_candidates(), "finish_coverage": finish_coverage()}
    if request.method == "POST":
        selected_id = request.POST.get("opportunity", "")
        selected = next((item for item in opportunities if item["opportunity_id"] == selected_id), None)
        if selected is None:
            raise Http404("Peluang tidak ditemukan")
        context["summary_opportunity_id"] = selected_id
        try:
            context["ai_summary"] = generate_opportunity_summary(selected)
            context["summary_source"] = "Ringkasan AI · FormuSense R&D"
        except AIUnavailable:
            context["ai_summary"] = (
                f"Konsep {selected['target_shade_name']} memiliki {selected['demo_interest']} "
                f"sinyal minat positif dan {selected['local_requests']} permintaan lokal. "
                "Tim formulasi perlu meninjau bukti dan menguji prototipe di lab."
            )
            context["summary_source"] = "Ringkasan aturan · AI tidak tersedia"
    return render(request, "research/unmet_demand.html", context)


@research_required
def evidence(request):
    return render(request, "research/evidence.html", {
        **evidence_data(request.GET.get("opportunity")), "team_feedback": feedback_summary(),
    })


@research_required
def formula_lab(request):
    """Render the formula brief for an opportunity, or for a gap candidate.

    If a `gap` index is present in the request, this renders the formula
    brief for that team gap candidate instead of the opportunity-based flow
    below (see build_gap_formula_brief in services/team_data.py) and returns
    early.

    Otherwise, build_formula_brief() is 100% deterministic (Lab-distance
    lookup against base_formula_reference.csv, see services/formula_lab.py).
    Its brief always carries needs_target_color / needs_reference booleans --
    when either is true there is no valid baseline to narrate an adjustment
    from, so generate_formula_rationale is skipped entirely rather than
    called on incomplete data (it would KeyError on brief["baseline"]
    regardless).
    """
    raw_gap = (request.POST if request.method == "POST" else request.GET).get("gap")
    if raw_gap is not None:
        if not raw_gap.isdigit() or int(raw_gap) >= len(gap_candidates()):
            raise Http404("Kandidat gap tidak ditemukan")
        gap = gap_candidates()[int(raw_gap)]
        context = {"selected_gap": gap, "opportunities": opportunity_data()}
        if request.method == "POST":
            context["team_brief"] = build_gap_formula_brief(int(raw_gap))
        return render(request, "research/formula_lab.html", context)
    opportunities = opportunity_data()
    selected_id = (request.POST if request.method == "POST" else request.GET).get("opportunity", "OPP001")
    if selected_id not in {item["opportunity_id"] for item in opportunities}:
        raise Http404("Peluang tidak ditemukan")
    context = {"opportunities": opportunities, "selected_id": selected_id,
               "selected_opportunity": next(item for item in opportunities if item["opportunity_id"] == selected_id)}
    if request.method == "POST":
        context.update(build_formula_brief(selected_id))
        brief = context["brief"]
        if brief["needs_target_color"]:
            context["formula_rationale"] = None
            context["rationale_source"] = (
                "NEEDS_TARGET_COLOR · belum ada swatch target untuk konsep ini"
            )
        elif brief["needs_reference"]:
            context["formula_rationale"] = None
            context["rationale_source"] = (
                "NEEDS_REFERENCE · tidak ada formula referensi yang cukup dekat warnanya"
            )
        else:
            try:
                context["formula_rationale"] = generate_formula_rationale(brief)
                context["rationale_source"] = "Penjelasan AI · perlu validasi formulator"
            except AIUnavailable:
                baseline = brief["baseline"]
                context["formula_rationale"] = (
                    f"Mulai dari formula referensi terdekat ({baseline['shade_name']}, "
                    f"jarak warna {baseline['distance']} dE dari target) dan sesuaikan "
                    "menuju arah yang diinginkan; perlu validasi formulator."
                )
                context["rationale_source"] = "Arah aturan · AI tidak tersedia"
    return render(request, "research/formula_lab.html", context)