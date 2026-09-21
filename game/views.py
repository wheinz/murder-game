from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from core.auth import get_trip, player_required
from core.models import Player

from . import engine
from .engine import GameError
from .models import Kill, KillAttempt, Location, Weapon


def _game_context(request):
    trip = request.trip
    player = request.current_player
    must_resolve, waiting_on = engine.pending_attempts_for(trip, player)

    kills = list(
        Kill.objects.filter(trip=trip, game_number=trip.game_number).select_related(
            "killer", "victim"
        )
    )
    kills_by_victim = {kill.victim_id: kill for kill in kills}
    my_kills = [kill for kill in kills if kill.killer_id == player.pk]
    out_players = [
        (p, kills_by_victim.get(p.pk)) for p in trip.players.filter(is_alive=False)
    ]

    def death_order(pair):
        kill = pair[1]
        return (kill is not None, kill.confirmed_at if kill else None)

    if trip.game_status == trip.GameStatus.FINISHED:
        standings = engine.final_standings(trip, kills=kills)
        winner = next((row["player"] for row in standings if row["winner"]), None)
    else:
        standings = sorted(out_players, key=death_order, reverse=True)
        winner = None

    return {
        "trip": trip,
        "player": player,
        "assignment": player.active_assignment,
        "must_resolve": must_resolve,
        "waiting_on": waiting_on,
        "alive_count": trip.alive_players.count(),
        "total_count": trip.players.count(),
        "alive_players": trip.players.filter(is_alive=True),
        "out_players": out_players,
        "standings": standings,
        "my_kills": my_kills,
        "my_kill_count": len(my_kills),
        "killed_by": kills_by_victim.get(player.pk),
        "winner": winner,
    }


@player_required
def game(request, code):
    return render(request, "game/game.html", _game_context(request))


def rules(request, code):
    trip = get_trip(request, code)
    return render(request, "game/rules.html", {"trip": trip})


def _pool_context(request, error=None):
    trip = request.trip
    return {
        "trip": trip,
        "error": error,
        "weapons": trip.weapons.filter(is_active=True, submitted_by=request.current_player),
        "locations": trip.locations.filter(
            is_active=True, submitted_by=request.current_player
        ),
    }


@player_required
def pool(request, code):
    trip = request.trip
    if request.method == "POST":
        text = request.POST.get("text", "").strip()
        kind = request.POST.get("kind", "weapon")
        error = None
        if not text:
            error = "Enter a weapon or location first."
        elif kind == "location":
            _, created = Location.objects.get_or_create(
                trip=trip, text=text, defaults={"submitted_by": request.current_player}
            )
            if not created:
                error = "That location has already been added."
        else:
            _, created = Weapon.objects.get_or_create(
                trip=trip, text=text, defaults={"submitted_by": request.current_player}
            )
            if not created:
                error = "That weapon has already been added."

        if request.headers.get("HX-Request"):
            context = _pool_context(request, error)
            return render(request, "game/partials/pool_lists.html", context)
        if error:
            messages.error(request, error)
        return redirect("game:pool", code=code)

    return render(request, "game/pool.html", _pool_context(request))


@player_required
def attempt_new(request, code):
    if request.method != "POST":
        return redirect("game:game", code=code)
    counterpart_id = request.POST.get("counterpart")
    counterpart = get_object_or_404(Player, pk=counterpart_id, trip=request.trip)
    try:
        engine.create_attempt(request.trip, request.current_player, counterpart)
        messages.success(request, "Kill reported. Waiting for the other player to confirm.")
    except GameError as exc:
        messages.error(request, str(exc))
    return redirect("game:game", code=code)


@player_required
def report_death(request, code):
    if request.method != "POST":
        return redirect("game:game", code=code)
    try:
        engine.report_death(request.trip, request.current_player)
        messages.success(request, "You're out.")
    except GameError as exc:
        messages.error(request, str(exc))
    return redirect("game:game", code=code)


@player_required
def attempt_resolve(request, code, attempt_id, decision):
    attempt = get_object_or_404(KillAttempt, pk=attempt_id, trip=request.trip)
    if request.method != "POST":
        return redirect("game:game", code=code)
    try:
        engine.resolve_attempt(
            attempt, request.current_player, confirmed=(decision == "confirm")
        )
        if decision == "confirm":
            messages.success(request, "Kill confirmed.")
        else:
            messages.warning(request, "Kill denied.")
    except GameError as exc:
        messages.error(request, str(exc))
    return redirect("game:game", code=code)
