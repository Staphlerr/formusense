from django.urls import path

from accounts import views


app_name = "accounts"
urlpatterns = [
    path("register/", views.register, name="register"),
    path("consumer/login/", views.consumer_login, name="consumer_login"),
    path("rd/login/", views.rd_login, name="rd_login"),
    path("logout/", views.sign_out, name="logout"),
]
