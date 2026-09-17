from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("rd/", include("research.urls")),
    path("", include("consumer.urls")),
]
