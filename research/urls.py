from django.urls import path

from research import views


app_name = "research"
urlpatterns = [
    path("", views.overview, name="overview"),
    path("unmet-demand/", views.unmet_demand, name="unmet_demand"),
    path("evidence/", views.evidence, name="evidence"),
    path("formula-lab/", views.formula_lab, name="formula_lab"),
]
