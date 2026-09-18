from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from feed.models import Post

from .auth import (
    get_current_player,
    get_trip,
    set_current_player,
    start_impersonation,
    stop_impersonation,
)
from .models import Player, Trip


def home(request):
    player = get_current_player(request)
    if player is not None:
        return redirect("game:game", code=player.trip.code)

    if request.method == "POST":
        code = request.POST.get("code", "").strip()
        if not (len(code) == 6 and code.isdigit()):
            messages.error(request, "Enter the 6-digit code.")
        else:
            trip = Trip.objects.filter(code=code).first()
            if trip is None:
                messages.error(request, "No game matches that code.")
            else:
                return redirect("game:game", code=trip.code)

    return render(request, "core/home.html")


@require_http_methods(["GET", "POST"])
def join(request, code):
    trip = get_trip(request, code)
    player = get_current_player(request)
    if player and player.trip_id == trip.pk:
        return redirect("game:game", code=trip.code)

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if request.POST.get("action") == "rejoin":
            pin = request.POST.get("pin", "").strip()
            if not name:
                messages.error(request, "Enter your nickname first.")
            elif not (len(pin) == 4 and pin.isdigit()):
                messages.error(request, "Enter your 4-digit player code.")
            else:
                player = trip.players.filter(name__iexact=name, pin=pin).first()
                if player is None:
                    messages.error(
                        request, "That nickname and player code don't match anyone here."
                    )
                else:
                    set_current_player(request, player)
                    messages.success(request, f"Welcome back, {player.name}.")
                    return redirect("game:game", code=trip.code)
        elif not name:
            messages.error(request, "Enter a nickname first.")
        elif len(name) > 80:
            messages.error(request, "That nickname is too long (80 characters max).")
        elif trip.players.filter(name__iexact=name).exists():
            messages.error(request, f"“{name}” is already taken in this game.")
        else:
            new_player = Player.objects.create(trip=trip, name=name)
            set_current_player(request, new_player)
            Post.system(trip, f"{new_player.name} joined the game.", author=new_player)
            return redirect("game:game", code=trip.code)

    return render(request, "core/join.html", {"trip": trip})


@staff_member_required
def impersonate(request, player_id):
    player = get_object_or_404(Player, pk=player_id)
    start_impersonation(request, player)
    messages.info(request, f"Now viewing as {player.name}.")
    return redirect("game:game", code=player.trip.code)


@staff_member_required
def stop_impersonating(request):
    stop_impersonation(request)
    messages.info(request, "Stopped viewing as player.")
    return redirect("admin:index")
