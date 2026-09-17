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
    path("my-profile/", views.account_profile, name="account_profile"),
    path("my-profile/shades/", views.save_shade, name="save_shade"),
    path("my-profile/photos/", views.save_photo, name="save_photo"),
    path("my-profile/photos/<int:photo_id>/", views.profile_photo, name="profile_photo"),
    path("my-profile/photos/<int:photo_id>/delete/", views.delete_photo, name="delete_photo"),
    path("recommendations/", views.recommendations, name="recommendations"),
    path("feedback/success/", views.feedback_success, name="feedback_success"),
    path("feedback/<str:shade_id>/", views.feedback, name="feedback"),
    path("how-it-works/", views.how_it_works, name="how_it_works"),
]
