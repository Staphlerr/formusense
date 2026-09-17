from django.http import Http404
from django.shortcuts import render

from accounts.access import research_required
from services.ai_client import AIUnavailable, generate_formula_rationale, generate_opportunity_summary
from services.analytics import evidence as evidence_data
from services.analytics import overview as overview_data
from services.analytics import opportunities as opportunity_data
from services.formula_lab import build_formula_brief
from services.dataset_insights import dataset_insights


@research_required
def overview(request):
    return render(request, "research/overview.html", {
        **overview_data(), "datasets": dataset_insights(),
    })


@research_required
def unmet_demand(request):
    opportunities = opportunity_data()
    context = {"opportunities": opportunities}
    if request.method == "POST":
        selected_id = request.POST.get("opportunity", "")
        selected = next((item for item in opportunities if item["opportunity_id"] == selected_id), None)
        if selected is None:
            raise Http404("Peluang tidak ditemukan")
        context["summary_opportunity_id"] = selected_id
        try:
            context["ai_summary"] = generate_opportunity_summary(selected)
            context["summary_source"] = "Ringkasan AI · data demo + feedback lokal"
        except AIUnavailable:
            context["ai_summary"] = (
                f"Konsep {selected['target_shade_name']} memiliki {selected['demo_interest']} "
                f"sinyal minat demo dan {selected['local_requests']} permintaan lokal. "
                "Tim formulasi perlu meninjau bukti dan menguji prototipe di lab."
            )
            context["summary_source"] = "Ringkasan aturan · AI tidak tersedia"
    return render(request, "research/unmet_demand.html", context)


@research_required
def evidence(request):
    return render(request, "research/evidence.html", evidence_data(request.GET.get("opportunity")))


@research_required
def formula_lab(request):
    opportunities = opportunity_data()
    selected_id = (request.POST if request.method == "POST" else request.GET).get("opportunity", "OPP001")
    if selected_id not in {item["opportunity_id"] for item in opportunities}:
        raise Http404("Peluang tidak ditemukan")
    context = {"opportunities": opportunities, "selected_id": selected_id,
               "selected_opportunity": next(item for item in opportunities if item["opportunity_id"] == selected_id)}
    if request.method == "POST":
        context.update(build_formula_brief(selected_id))
        try:
            context["formula_rationale"] = generate_formula_rationale(context["brief"])
            context["rationale_source"] = "Penjelasan AI · perlu validasi formulator"
        except AIUnavailable:
            context["formula_rationale"] = context["brief"]["base_direction"]
            context["rationale_source"] = "Arah aturan · AI tidak tersedia"
    return render(request, "research/formula_lab.html", context)
