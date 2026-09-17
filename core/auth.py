from functools import wraps

from django.shortcuts import get_object_or_404, redirect

from .models import Player, Trip

IMPERSONATE_KEY = "impersonate_player_id"


def _is_staff(request):
    user = getattr(request, "user", None)
    return bool(user and user.is_authenticated and user.is_staff)


def get_impersonated_player(request):
    if not request.session.session_key or not _is_staff(request):
        return None
    player_id = request.session.get(IMPERSONATE_KEY)
    if not player_id:
        return None
    return Player.objects.select_related("trip").filter(pk=player_id).first()


def get_current_player(request):
    if not request.session.session_key:
        return None
    impersonated = get_impersonated_player(request)
    if impersonated is not None:
        return impersonated
    player_id = request.session.get("player_id")
    if not player_id:
        return None
    return Player.objects.select_related("trip").filter(pk=player_id).first()


def set_current_player(request, player):
    request.session["player_id"] = player.pk
    request.session.cycle_key()
    request.current_player = player


def start_impersonation(request, player):
    request.session[IMPERSONATE_KEY] = player.pk
    request.session.cycle_key()
    request.current_player = player


def stop_impersonation(request):
    request.session.pop(IMPERSONATE_KEY, None)
    request.current_player = None


def get_trip(request, code):
    return get_object_or_404(Trip, code=code)


def player_required(view):
    @wraps(view)
    def wrapper(request, code, *args, **kwargs):
        trip = get_trip(request, code)
        player = get_current_player(request)
        if player is None or player.trip_id != trip.pk:
            return redirect("core:join", code=trip.code)
        request.current_player = player
        request.trip = trip
        return view(request, code, *args, **kwargs)

    return wrapper
