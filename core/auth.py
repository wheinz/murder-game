from functools import wraps

from django.shortcuts import get_object_or_404, redirect

from .models import Player, Trip


def get_current_player(request):
    if not request.session.session_key:
        return None
    player_id = request.session.get("player_id")
    if not player_id:
        return None
    return Player.objects.select_related("trip").filter(pk=player_id).first()


def set_current_player(request, player):
    request.session["player_id"] = player.pk
    request.session.cycle_key()
    request.current_player = player


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
