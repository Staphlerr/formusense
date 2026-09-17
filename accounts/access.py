from functools import wraps

from django.core.exceptions import PermissionDenied
from django.shortcuts import resolve_url
from django.contrib.auth.views import redirect_to_login


CONSUMER_GROUP = "consumer"
RESEARCH_GROUP = "rd"
CONSUMER_SESSION_KEYS = (
    "basic_profile", "photo_consent", "preference", "photo_scanned",
    "lip_profile", "personal_note_cache", "last_feedback",
)


def has_consumer_access(user):
    return user.is_authenticated and user.groups.filter(name=CONSUMER_GROUP).exists()


def has_research_access(user):
    return user.is_authenticated and (
        user.is_superuser or user.groups.filter(name=RESEARCH_GROUP).exists()
    )


def _role_required(check, login_view):
    def decorate(view):
        @wraps(view)
        def protected(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path(), resolve_url(login_view))
            if not check(request.user):
                raise PermissionDenied("Akun ini tidak memiliki akses ke area tersebut.")
            return view(request, *args, **kwargs)
        return protected
    return decorate


consumer_required = _role_required(has_consumer_access, "accounts:consumer_login")
research_required = _role_required(has_research_access, "accounts:rd_login")


def clear_consumer_session(request):
    for key in CONSUMER_SESSION_KEYS:
        request.session.pop(key, None)
