import random

from django.db import transaction
from django.utils import timezone

from feed.models import Post

from .models import Assignment, Kill, KillAttempt


class GameError(Exception):
    """Raised when a game action is not allowed in the current state."""


def _assign_items(players, items):
    """Hand each player one item, avoiding their own submission where possible."""
    remaining = list(items)
    random.shuffle(remaining)
    result = {}
    ordered = sorted(
        players,
        key=lambda p: sum(1 for i in remaining if i.submitted_by_id != p.pk),
    )
    for player in ordered:
        choices = [i for i in remaining if i.submitted_by_id != player.pk]
        if not choices:
            choices = remaining
        chosen = random.choice(choices)
        remaining.remove(chosen)
        result[player.pk] = chosen.text
    return result


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
        Assignment.objects.create(
            trip=trip,
            killer=attempt.killer,
            target=next_target,
            weapon_text=victim_contract.weapon_text,
            location_text=victim_contract.location_text,
            game_number=attempt.game_number,
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

    alive = list(trip.alive_players)
    if len(alive) == 1:
        Post.system(trip, f"The hunt is over. {alive[0].name} wins!")
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
