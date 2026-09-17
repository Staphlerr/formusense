from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django import forms


class ConsumerRegistrationForm(UserCreationForm):
    email = forms.EmailField(label="Email", required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")
        labels = {"username": "Nama pengguna"}
