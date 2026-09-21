import random

from django.db import transaction
from django.utils import timezone

from feed.models import Post

from .models import Assignment, Kill, KillAttempt, Loadout


class GameError(Exception):
    """Raised when a game action is not allowed in the current state."""


def _assign_items(players, items):
    """Hand each player one item from the pool, without replacement."""
    remaining = list(items)
    random.shuffle(remaining)
    return {player.pk: remaining[i].text for i, player in enumerate(players)}


def start_game(trip):
    players = list(trip.players.all())
    if len(players) < 3:
        raise GameError("You need at least 3 players to start.")

    weapons = list(trip.weapons.filter(is_active=True))
    locations = list(trip.locations.filter(is_active=True))
    if len(weapons) < len(players):
        raise GameError(f"Add at least {len(players)} weapons, currently {len(weapons)}.")
    if len(locations) < len(players):
        raise GameError(
            f"Add at least {len(players)} locations, currently {len(locations)}."
        )

    with transaction.atomic():
        now = timezone.now()
        if trip.game_number == 0:
            trip.game_number = 1
        trip.assignments.filter(is_active=True).update(is_active=False, ended_at=now)
        trip.kill_attempts.filter(status=KillAttempt.Status.PENDING).update(
            status=KillAttempt.Status.DENIED, resolved_at=now
        )
        trip.players.update(is_alive=True)

        chain = players[:]
        random.shuffle(chain)
        weapon_map = _assign_items(players, weapons)
        location_map = _assign_items(players, locations)

        count = len(chain)
        for index, killer in enumerate(chain):
            target = chain[(index + 1) % count]
            Assignment.objects.create(
                trip=trip,
                killer=killer,
                target=target,
                weapon_text=weapon_map[killer.pk],
                location_text=location_map[killer.pk],
                game_number=trip.game_number,
            )

        trip.game_status = trip.GameStatus.ACTIVE
        trip.save(update_fields=["game_status", "game_number"])

    Post.system(trip, "The hunt has begun. Check your contract.")
    return True


def grant_bonus(trip):
    """Give every active contract an extra weapon/location pair. Repeatable."""
    if trip.game_status != trip.GameStatus.ACTIVE:
        raise GameError("Bonuses can only be granted while the hunt is active.")

    assignments = list(trip.assignments.filter(is_active=True).select_related("killer"))
    if not assignments:
        raise GameError("There are no active contracts.")

    weapons = list(trip.weapons.filter(is_active=True))
    locations = list(trip.locations.filter(is_active=True))
    if not weapons or not locations:
        raise GameError("Add at least one weapon and one location first.")

    with transaction.atomic():
        for assignment in assignments:
            Loadout.objects.create(
                assignment=assignment,
                weapon_text=random.choice(weapons).text,
                location_text=random.choice(locations).text,
            )

    Post.system(trip, "Bonus! Every hunter gains an extra weapon and location.")
    return len(assignments)


def _killer_for(victim):
    assignment = victim.assignments_received.filter(is_active=True).first()
    return assignment.killer if assignment else None


def create_attempt(trip, killer, victim):
    """The killer reports a kill; the victim must confirm or deny it."""
    if killer.trip_id != trip.pk or victim.trip_id != trip.pk:
        raise GameError("Both players must belong to this game.")
    if killer.pk == victim.pk:
        raise GameError("You cannot target yourself.")

    assignment = killer.assignments_given.filter(is_active=True).first()
    if assignment is None or assignment.target_id != victim.pk:
        raise GameError("That player is not your target.")

    if KillAttempt.objects.filter(
        trip=trip, killer=killer, victim=victim, status=KillAttempt.Status.PENDING
    ).exists():
        raise GameError(
            "A kill has already been reported for this contract. Wait for confirmation."
        )

    attempt = KillAttempt.objects.create(
        trip=trip,
        killer=killer,
        victim=victim,
        initiated_by=killer,
        weapon_text=assignment.weapon_text,
        location_text=assignment.location_text,
        game_number=trip.game_number,
    )
    Post.system(
        trip,
        f"Kill reported: {killer.name} → {victim.name}. Waiting for confirmation.",
    )
    return attempt


@transaction.atomic
def report_death(trip, victim):
    """The victim declares their own death. No confirmation needed; applied at once."""
    incoming = victim.assignments_received.filter(is_active=True).first()
    if incoming is None:
        raise GameError("No one is hunting you right now.")

    killer = incoming.killer
    attempt = KillAttempt.objects.filter(
        trip=trip,
        killer=killer,
        victim=victim,
        status=KillAttempt.Status.PENDING,
    ).first()
    if attempt is None:
        attempt = KillAttempt.objects.create(
            trip=trip,
            killer=killer,
            victim=victim,
            initiated_by=victim,
            weapon_text=incoming.weapon_text,
            location_text=incoming.location_text,
            game_number=trip.game_number,
        )
    return resolve_attempt(attempt, victim, confirmed=True)


@transaction.atomic
def resolve_attempt(attempt, resolver, confirmed):
    attempt = KillAttempt.objects.select_for_update().get(pk=attempt.pk)
    if attempt.status != KillAttempt.Status.PENDING:
        raise GameError("This kill report has already been confirmed or denied.")

    is_party = resolver.pk in {attempt.killer_id, attempt.victim_id}
    if not is_party:
        raise GameError("Only the players involved can confirm or deny this kill.")

    trip = attempt.trip
    now = timezone.now()

    if not confirmed:
        attempt.status = KillAttempt.Status.DENIED
        attempt.resolved_at = now
        attempt.save(update_fields=["status", "resolved_at"])
        Post.system(
            trip,
            f"Kill denied: {attempt.killer.name} vs {attempt.victim.name}.",
        )
        return None

    assignment = attempt.killer.assignments_given.filter(is_active=True).first()
    if (
        assignment is None
        or assignment.target_id != attempt.victim_id
        or not attempt.victim.is_alive
    ):
        raise GameError("That contract is no longer valid.")

    victim_contract = attempt.victim.assignments_given.filter(is_active=True).first()
    next_target = victim_contract.target if victim_contract else None

    weapon_text = attempt.weapon_text or assignment.weapon_text
    location_text = attempt.location_text or assignment.location_text

    assignment.close()
    attempt.victim.is_alive = False
    attempt.victim.save(update_fields=["is_alive"])
    if victim_contract:
        victim_contract.close()

    kill = Kill.objects.create(
        trip=trip,
        killer=attempt.killer,
        victim=attempt.victim,
        weapon_text=weapon_text,
        location_text=location_text,
        game_number=attempt.game_number,
    )

    attempt.status = KillAttempt.Status.CONFIRMED
    attempt.resolved_at = now
    attempt.save(update_fields=["status", "resolved_at"])

    game_over = (
        next_target is None
        or next_target.pk == attempt.killer_id
        or trip.alive_players.count() <= 1
    )

    if game_over:
        trip.game_status = trip.GameStatus.FINISHED
        trip.save(update_fields=["game_status"])
        Post.system(
            trip,
            f"{attempt.victim.name} is down. {attempt.killer.name} wins the hunt!",
        )
    else:
        new_contract = Assignment.objects.create(
            trip=trip,
            killer=attempt.killer,
            target=next_target,
            weapon_text=victim_contract.weapon_text,
            location_text=victim_contract.location_text,
            game_number=attempt.game_number,
        )
        for loadout in victim_contract.loadouts.all():
            Loadout.objects.create(
                assignment=new_contract,
                weapon_text=loadout.weapon_text,
                location_text=loadout.location_text,
            )
        Post.system(
            trip,
            f"{attempt.victim.name} is down. "
            f"{attempt.killer.name} inherits a new contract.",
        )

    _cancel_stale_attempts(trip, exclude=attempt)
    return kill


def _cancel_stale_attempts(trip, exclude=None):
    pending = trip.kill_attempts.filter(status=KillAttempt.Status.PENDING)
    if exclude is not None:
        pending = pending.exclude(pk=exclude.pk)
    for attempt in pending:
        assignment = attempt.killer.assignments_given.filter(is_active=True).first()
        if (
            assignment is None
            or assignment.target_id != attempt.victim_id
            or not attempt.victim.is_alive
        ):
            attempt.status = KillAttempt.Status.DENIED
            attempt.resolved_at = timezone.now()
            attempt.save(update_fields=["status", "resolved_at"])


def round_start(trip):
    """When the current round's contracts were first dealt."""
    start = (
        trip.assignments.filter(game_number=trip.game_number)
        .order_by("created_at")
        .values_list("created_at", flat=True)
        .first()
    )
    return start or timezone.now()


def _elapsed_display(times, start):
    if not times:
        return None
    seconds = max(0, (max(times) - start).total_seconds())
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes} min"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes} min"


def final_standings(trip, kills=None):
    """Ranked rows for a finished hunt: living by kills, then the dead.

    Living players rank by kill count, then by who reached their last kill
    soonest after the round began. Dead players follow, latest elimination first.
    """
    if kills is None:
        kills = list(
            Kill.objects.filter(trip=trip, game_number=trip.game_number).select_related(
                "killer", "victim"
            )
        )
    kills_by_victim = {kill.victim_id: kill for kill in kills}

    kill_times = {}
    for kill in kills:
        kill_times.setdefault(kill.killer_id, []).append(kill.confirmed_at)

    start = round_start(trip)

    def living_key(player):
        times = sorted(kill_times.get(player.pk, []))
        elapsed = (times[-1] - start).total_seconds() if times else float("inf")
        return (-len(times), elapsed, player.name)

    living = sorted(trip.players.filter(is_alive=True), key=living_key)
    winner_pk = living[0].pk if living else None

    rows = [
        {
            "player": player,
            "kills": len(kill_times.get(player.pk, [])),
            "alive": True,
            "kill": None,
            "winner": player.pk == winner_pk,
            "elapsed": _elapsed_display(kill_times.get(player.pk, []), start),
        }
        for player in living
    ]

    def death_order(player):
        kill = kills_by_victim.get(player.pk)
        return (kill is not None, kill.confirmed_at if kill else None)

    dead = trip.players.filter(is_alive=False)
    for player in sorted(dead, key=death_order, reverse=True):
        rows.append(
            {
                "player": player,
                "kills": len(kill_times.get(player.pk, [])),
                "alive": False,
                "kill": kills_by_victim.get(player.pk),
                "winner": False,
                "elapsed": None,
            }
        )
    return rows


def winner_of(trip):
    """The winning player of a finished hunt, or None."""
    if trip.game_status != trip.GameStatus.FINISHED:
        return None
    standings = final_standings(trip)
    if standings and standings[0]["alive"]:
        return standings[0]["player"]
    return None


def end_game(trip):
    """Finalize the hunt with whatever players are still alive (used by admins)."""
    now = timezone.now()
    with transaction.atomic():
        trip.assignments.filter(is_active=True).update(is_active=False, ended_at=now)
        trip.kill_attempts.filter(status=KillAttempt.Status.PENDING).update(
            status=KillAttempt.Status.DENIED, resolved_at=now
        )
        trip.game_status = trip.GameStatus.FINISHED
        trip.save(update_fields=["game_status"])

    winner = winner_of(trip)
    if winner is not None:
        Post.system(trip, f"The hunt is over. {winner.name} wins!")
    else:
        Post.system(trip, "The hunt was ended early.")


def reset_game(trip):
    now = timezone.now()
    with transaction.atomic():
        trip.assignments.filter(is_active=True).update(is_active=False, ended_at=now)
        trip.kill_attempts.filter(status=KillAttempt.Status.PENDING).update(
            status=KillAttempt.Status.DENIED, resolved_at=now
        )
        trip.players.update(is_alive=True)
        trip.game_number += 1
        trip.game_status = trip.GameStatus.SETUP
        trip.save(update_fields=["game_status", "game_number"])
    Post.system(trip, "The game was reset.")


def pending_attempts_for(trip, player):
    """Split a player's pending reports into ones they must answer vs. wait on."""
    attempts = KillAttempt.objects.filter(
        trip=trip,
        game_number=trip.game_number,
        status=KillAttempt.Status.PENDING,
    ).select_related("killer", "victim", "initiated_by")
    mine = [a for a in attempts if player.pk in {a.killer_id, a.victim_id}]
    must_resolve = [a for a in mine if a.awaiting.pk == player.pk]
    return must_resolve, [a for a in mine if a not in must_resolve]
