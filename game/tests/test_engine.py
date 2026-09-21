from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import Player
from feed.models import Post
from game import engine
from game.engine import GameError
from game.models import Assignment, Kill, KillAttempt, Location, Weapon


def add_pool(trip, n):
    for i in range(n):
        Weapon.objects.create(trip=trip, text=f"Weapon {i}")
        Location.objects.create(trip=trip, text=f"Place {i}")


def build_chain(trip, players):
    """Create a deterministic active chain: p0->p1->p2->...->p0."""
    for i, killer in enumerate(players):
        Assignment.objects.create(
            trip=trip,
            killer=killer,
            target=players[(i + 1) % len(players)],
            weapon_text=f"weapon-{i}",
            location_text=f"place-{i}",
        )


def test_start_game_creates_one_cycle(trip, players):
    add_pool(trip, len(players))
    engine.start_game(trip)

    trip.refresh_from_db()
    assert trip.game_status == trip.GameStatus.ACTIVE
    assert trip.assignments.filter(is_active=True).count() == len(players)

    # Every player targets exactly one other and is targeted once -> single cycle.
    targets = {a.killer_id: a.target_id for a in trip.assignments.filter(is_active=True)}
    assert set(targets) == {p.pk for p in players}
    assert len(set(targets.values())) == len(players)
    assert all(targets[k] != k for k in targets)

    some = players[0]
    reached = {some.pk}
    cursor = targets[some.pk]
    while cursor != some.pk:
        reached.add(cursor)
        cursor = targets[cursor]
    assert reached == {p.pk for p in players}


def test_start_requires_three_players(trip):
    Player.objects.create(trip=trip, name="Solo")
    with pytest.raises(GameError):
        engine.start_game(trip)


def test_start_requires_enough_pool(trip, players):
    add_pool(trip, 1)
    with pytest.raises(GameError):
        engine.start_game(trip)


def test_kill_transfers_victim_contract(trip, players):
    add_pool(trip, len(players))
    build_chain(trip, players)
    alice, bob, cara, dan = players
    # chain: alice->bob->cara->dan->alice
    attempt = engine.create_attempt(trip, alice, bob)
    engine.resolve_attempt(attempt, bob, confirmed=True)

    bob.refresh_from_db()
    alice.refresh_from_db()
    assert bob.is_alive is False
    assert trip.kills.filter(killer=alice, victim=bob).exists()

    # Alice inherits Bob's contract: Bob was hunting Cara, so now Alice hunts Cara
    # using Bob's weapon/place.
    new_contract = alice.assignments_given.get(is_active=True)
    assert new_contract.target_id == cara.pk
    assert new_contract.weapon_text == "weapon-1"
    assert new_contract.location_text == "place-1"


def test_grant_bonus_adds_pair_to_every_contract(trip, players):
    add_pool(trip, len(players))
    engine.start_game(trip)

    granted = engine.grant_bonus(trip)

    assert granted == len(players)
    for assignment in trip.assignments.filter(is_active=True):
        assert assignment.loadouts.count() == 1
    assert Post.objects.filter(trip=trip, body__icontains="bonus").exists()


def test_grant_bonus_stacks_on_repeat(trip, players):
    add_pool(trip, len(players))
    engine.start_game(trip)

    engine.grant_bonus(trip)
    engine.grant_bonus(trip)

    for assignment in trip.assignments.filter(is_active=True):
        assert assignment.loadouts.count() == 2


def test_grant_bonus_requires_active_hunt(trip, players):
    add_pool(trip, len(players))
    with pytest.raises(GameError):
        engine.grant_bonus(trip)


def test_grant_bonus_requires_pool_items(trip, players):
    add_pool(trip, len(players))
    engine.start_game(trip)
    trip.weapons.update(is_active=False)

    with pytest.raises(GameError):
        engine.grant_bonus(trip)


def test_kill_inherits_victim_bonus_pairs(trip, players):
    add_pool(trip, len(players))
    build_chain(trip, players)  # alice -> bob -> cara -> dan -> alice
    alice, bob, cara = players[0], players[1], players[2]
    trip.game_status = trip.GameStatus.ACTIVE
    trip.save(update_fields=["game_status"])
    engine.grant_bonus(trip)

    bob_contract = bob.assignments_given.get(is_active=True)
    bob_pairs = list(bob_contract.loadouts.values_list("weapon_text", "location_text"))
    assert bob_pairs

    attempt = engine.create_attempt(trip, alice, bob)
    engine.resolve_attempt(attempt, bob, confirmed=True)

    new_contract = alice.assignments_given.get(is_active=True)
    assert new_contract.target_id == cara.pk
    new_pairs = list(new_contract.loadouts.values_list("weapon_text", "location_text"))
    assert new_pairs == bob_pairs


def test_last_standing_wins(trip, players):
    add_pool(trip, len(players))
    build_chain(trip, players)
    alice, bob, cara, dan = players
    # Reduce to alice->bob and bob->alice, then alice confirms.

    a1 = engine.create_attempt(trip, alice, bob)
    engine.resolve_attempt(a1, bob, confirmed=True)  # bob dead; alice now hunts cara
    a2 = engine.create_attempt(trip, alice, cara)
    engine.resolve_attempt(a2, cara, confirmed=True)  # cara dead; alice now hunts dan
    a3 = engine.create_attempt(trip, alice, dan)
    engine.resolve_attempt(a3, dan, confirmed=True)  # dan dead -> alice last standing

    trip.refresh_from_db()
    assert trip.game_status == trip.GameStatus.FINISHED
    assert trip.winner == alice
    assert trip.players.filter(is_alive=True).count() == 1
    assert Kill.objects.filter(trip=trip).count() == 3


def record_kill(trip, killer, victim, when):
    return Kill.objects.create(
        trip=trip,
        killer=killer,
        victim=victim,
        weapon_text="weapon",
        location_text="place",
        game_number=trip.game_number,
        confirmed_at=when,
    )


def make_contract(trip, killer, target, created_at):
    return Assignment.objects.create(
        trip=trip,
        killer=killer,
        target=target,
        weapon_text="weapon",
        location_text="place",
        created_at=created_at,
    )


def finish(trip):
    trip.game_status = trip.GameStatus.FINISHED
    trip.save(update_fields=["game_status"])


def test_winner_has_most_kills_among_living(trip, players):
    alice, bob, cara, dan = players
    start = timezone.now() - timedelta(hours=1)
    make_contract(trip, alice, bob, start)
    for player in (bob, cara):
        player.is_alive = False
        player.save(update_fields=["is_alive"])
    record_kill(trip, alice, bob, start + timedelta(minutes=5))
    record_kill(trip, alice, cara, start + timedelta(minutes=20))
    finish(trip)

    standings = engine.final_standings(trip)
    assert standings[0]["player"] == alice
    assert standings[0]["winner"] is True
    assert standings[0]["kills"] == 2
    assert engine.winner_of(trip) == alice


def test_winner_tiebreak_is_fastest_to_tally(trip, players):
    alice, bob, cara, dan = players
    start = timezone.now() - timedelta(hours=2)
    make_contract(trip, alice, bob, start)
    make_contract(trip, cara, dan, start)
    for player in (bob, dan):
        player.is_alive = False
        player.save(update_fields=["is_alive"])
    record_kill(trip, alice, bob, start + timedelta(minutes=10))
    record_kill(trip, cara, dan, start + timedelta(minutes=50))
    finish(trip)

    standings = engine.final_standings(trip)
    assert standings[0]["player"] == alice
    assert standings[0]["winner"] is True
    assert standings[1]["player"] == cara
    assert [row["alive"] for row in standings] == [True, True, False, False]


def test_last_survivor_wins_even_without_kills(trip, players):
    alice, bob, cara, dan = players
    start = timezone.now() - timedelta(hours=1)
    make_contract(trip, alice, dan, start)
    for player in (bob, cara, dan):
        player.is_alive = False
        player.save(update_fields=["is_alive"])
    record_kill(trip, bob, cara, start + timedelta(minutes=5))
    finish(trip)

    assert engine.winner_of(trip) == alice
    assert trip.winner == alice


def test_end_game_announces_ranked_winner(trip, players):
    add_pool(trip, len(players))
    engine.start_game(trip)

    engine.end_game(trip)

    trip.refresh_from_db()
    assert trip.game_status == trip.GameStatus.FINISHED
    # Everyone is alive with no kills, so the tie-break falls to nickname order.
    assert trip.winner == players[0]
    assert Post.objects.filter(trip=trip, body__icontains="wins").exists()


def test_report_death_resolves_immediately(trip, players):
    add_pool(trip, len(players))
    build_chain(trip, players)  # alice -> bob -> cara -> dan -> alice
    alice, bob, cara = players[0], players[1], players[2]

    engine.report_death(trip, bob)

    bob.refresh_from_db()
    assert bob.is_alive is False
    assert Kill.objects.filter(trip=trip, killer=alice, victim=bob).exists()
    # alice inherits bob's contract (bob was hunting cara)
    new_contract = alice.assignments_given.get(is_active=True)
    assert new_contract.target_id == cara.pk
    assert not KillAttempt.objects.filter(
        trip=trip, status=KillAttempt.Status.PENDING
    ).exists()


def test_report_death_without_contract_raises(trip, players):
    with pytest.raises(GameError):
        engine.report_death(trip, players[0])


def test_denied_attempt_keeps_game_unchanged(trip, players):
    add_pool(trip, len(players))
    build_chain(trip, players)
    alice, bob = players[0], players[1]
    attempt = engine.create_attempt(trip, alice, bob)
    engine.resolve_attempt(attempt, bob, confirmed=False)

    attempt.refresh_from_db()
    bob.refresh_from_db()
    assert attempt.status == KillAttempt.Status.DENIED
    assert bob.is_alive is True
    assert alice.assignments_given.get(is_active=True).target_id == bob.pk


def test_cannot_target_unrelated_player(trip, players):
    add_pool(trip, len(players))
    build_chain(trip, players)
    alice = players[0]
    cara = players[2]
    with pytest.raises(GameError):
        engine.create_attempt(trip, alice, cara)


def test_outside_party_cannot_resolve(trip, players):
    add_pool(trip, len(players))
    build_chain(trip, players)
    alice, bob, cara = players[0], players[1], players[2]
    attempt = engine.create_attempt(trip, alice, bob)
    with pytest.raises(GameError):
        engine.resolve_attempt(attempt, cara, confirmed=True)


def test_reset_rotates_round_and_preserves_history(trip, players):
    add_pool(trip, len(players))
    engine.start_game(trip)
    trip.refresh_from_db()
    first_round = trip.game_number
    assert first_round == 1

    alice = players[0]
    victim = alice.active_assignment.target
    attempt = engine.create_attempt(trip, alice, victim)
    engine.resolve_attempt(attempt, victim, confirmed=True)
    assert Kill.objects.filter(trip=trip, game_number=first_round).count() == 1

    engine.reset_game(trip)
    trip.refresh_from_db()
    assert trip.game_number == first_round + 1
    assert trip.game_status == trip.GameStatus.SETUP
    assert trip.players.filter(is_alive=False).count() == 0
    # previous round is preserved but scoped out
    assert Kill.objects.filter(trip=trip, game_number=first_round).count() == 1

    engine.start_game(trip)
    trip.refresh_from_db()
    assert trip.game_status == trip.GameStatus.ACTIVE
    assert trip.assignments.filter(
        is_active=True, game_number=trip.game_number
    ).count() == len(players)
    assert not trip.assignments.filter(is_active=True, game_number=first_round).exists()
    assert Kill.objects.filter(trip=trip, game_number=trip.game_number).count() == 0
