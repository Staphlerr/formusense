from django.urls import path

from consumer import views


app_name = "consumer"
urlpatterns = [
    path("", views.home, name="home"),
    path("profile/start/", views.profile_start, name="profile_start"),
    path("profile/consent/", views.consent, name="consent"),
    path("profile/preferences/", views.preferences, name="preferences"),
    path("profile/scan/", views.scan, name="scan"),
    path("profile/result/", views.profile_result, name="profile_result"),
    path("recommendations/", views.recommendations, name="recommendations"),
    path("feedback/success/", views.feedback_success, name="feedback_success"),
    path("feedback/<str:shade_id>/", views.feedback, name="feedback"),
    path("how-it-works/", views.how_it_works, name="how_it_works"),
]
