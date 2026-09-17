from urllib.parse import urlsplit

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.access import (
    CONSUMER_GROUP, clear_consumer_session, has_consumer_access,
    has_research_access,
)
from accounts.forms import ConsumerRegistrationForm


def _destination(request, role):
    default = "consumer:profile_start" if role == "consumer" else "research:overview"
    candidate = request.POST.get("next") or request.GET.get("next") or ""
    if not url_has_allowed_host_and_scheme(candidate, {request.get_host()}, require_https=request.is_secure()):
        return default
    path = urlsplit(candidate).path
    if role == "consumer" and path.startswith(("/profile/", "/recommendations/", "/feedback/")):
        return candidate
    if role == "rd" and path.startswith("/rd/"):
        return candidate
    return default


def register(request):
    if request.user.is_authenticated:
        if has_consumer_access(request.user):
            return redirect("consumer:profile_start")
        if has_research_access(request.user):
            return redirect("research:overview")
        raise PermissionDenied("Akun ini belum memiliki role.")
    form = ConsumerRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save(commit=False)
        user.email = form.cleaned_data["email"]
        user.save()
        group, _ = Group.objects.get_or_create(name=CONSUMER_GROUP)
        user.groups.add(group)
        clear_consumer_session(request)
        login(request, user)
        messages.success(request, "Akun konsumen berhasil dibuat.")
        return redirect("consumer:profile_start")
    return render(request, "accounts/register.html", {"form": form})


def _login(request, role):
    allowed = has_consumer_access if role == "consumer" else has_research_access
    if allowed(request.user):
        return redirect(_destination(request, role))
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        if not allowed(user):
            form.add_error(None, "Akun ini tidak memiliki akses ke area tersebut.")
        else:
            clear_consumer_session(request)
            login(request, user)
            return redirect(_destination(request, role))
    return render(request, "accounts/login.html", {
        "form": form, "role": role, "next": request.POST.get("next") or request.GET.get("next") or "",
    })


def consumer_login(request):
    return _login(request, "consumer")


def rd_login(request):
    return _login(request, "rd")


@require_POST
def sign_out(request):
    logout(request)
    return redirect("consumer:home")
