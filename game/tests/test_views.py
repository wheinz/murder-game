import pytest
from django.urls import reverse

from core.models import Player
from game import engine
from game.models import Kill, KillAttempt, Loadout, Location, Weapon


@pytest.fixture
def started(trip, players):
    for i in range(len(players)):
        Weapon.objects.create(trip=trip, text=f"Weapon {i}")
        Location.objects.create(trip=trip, text=f"Place {i}")
    engine.start_game(trip)
    return trip


def test_kill_attempt_and_confirm_over_http(client, started, login_as):
    killer = started.players.get(name="Alice")
    victim = Player.objects.get(pk=killer.active_assignment.target_id)

    login_as(client, killer)
    response = client.post(
        reverse("game:attempt_new", args=[started.code]),
        {"counterpart": victim.pk},
    )
    assert response.status_code == 302
    attempt = KillAttempt.objects.get(trip=started, killer=killer, victim=victim)
    assert attempt.status == KillAttempt.Status.PENDING

    victim_client = type(client)()
    login_as(victim_client, victim)
    response = victim_client.post(
        reverse("game:attempt_resolve", args=[started.code, attempt.pk, "confirm"])
    )
    assert response.status_code == 302

    victim.refresh_from_db()
    assert victim.is_alive is False
    assert Kill.objects.filter(trip=started, killer=killer, victim=victim).exists()


def test_pool_submission(client, trip, players, login_as):
    login_as(client, players[0])
    client.post(
        reverse("game:pool", args=[trip.code]),
        {"text": "Ketchup bottle", "kind": "weapon"},
    )
    assert trip.weapons.filter(text="Ketchup bottle").exists()


def test_rules_page_renders(client, trip):
    response = client.get(reverse("game:rules", args=[trip.code]))
    assert response.status_code == 200
    assert b"last one standing" in response.content.lower()


def test_rules_accessible_without_joining(client, trip):
    assert client.get(reverse("game:rules", args=[trip.code])).status_code == 200
    assert client.get(reverse("game:game", args=[trip.code])).status_code == 302


def test_pool_submission_location(client, trip, players, login_as):
    login_as(client, players[0])
    client.post(
        reverse("game:pool", args=[trip.code]),
        {"text": "The pool", "kind": "location"},
    )
    assert trip.locations.filter(text="The pool").exists()
    assert not trip.weapons.exists()


def test_duplicate_pool_submission_shows_inline_error(client, trip, players, login_as):
    login_as(client, players[0])
    Weapon.objects.create(trip=trip, text="Ketchup bottle")
    response = client.post(
        reverse("game:pool", args=[trip.code]),
        {"text": "Ketchup bottle", "kind": "weapon"},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    assert b"has already been added" in response.content
    assert trip.weapons.filter(text="Ketchup bottle").count() == 1


def test_pool_page_only_shows_own_submissions(client, trip, players, login_as):
    Weapon.objects.create(trip=trip, text="Alice bat", submitted_by=players[0])
    Weapon.objects.create(trip=trip, text="Bob knife", submitted_by=players[1])
    Location.objects.create(trip=trip, text="Alice attic", submitted_by=players[0])
    Location.objects.create(trip=trip, text="Bob cellar", submitted_by=players[1])

    login_as(client, players[0])
    response = client.get(reverse("game:pool", args=[trip.code]))
    assert response.status_code == 200
    assert b"Alice bat" in response.content
    assert b"Alice attic" in response.content
    assert b"Bob knife" not in response.content
    assert b"Bob cellar" not in response.content


def test_pool_partial_only_shows_own_submissions(client, trip, players, login_as):
    Weapon.objects.create(trip=trip, text="Alice bat", submitted_by=players[0])
    Weapon.objects.create(trip=trip, text="Bob knife", submitted_by=players[1])

    login_as(client, players[0])
    response = client.post(
        reverse("game:pool", args=[trip.code]),
        {"text": "Alice rope", "kind": "weapon"},
        HTTP_HX_REQUEST="true",
    )
    assert response.status_code == 200
    assert b"Alice bat" in response.content
    assert b"Alice rope" in response.content
    assert b"Bob knife" not in response.content


def confirm_kill(started):
    killer = started.players.get(name="Alice")
    victim = Player.objects.get(pk=killer.active_assignment.target_id)
    attempt = engine.create_attempt(started, killer, victim)
    engine.resolve_attempt(attempt, victim, confirmed=True)
    return killer, victim


def test_game_shows_eliminated_screen_for_dead_player(client, started, login_as):
    killer, victim = confirm_kill(started)
    login_as(client, victim)
    response = client.get(reverse("game:game", args=[started.code]))
    assert response.status_code == 200
    assert b"You're out" in response.content
    assert killer.name.encode() in response.content


def test_game_shows_my_kills(client, started, login_as):
    killer, victim = confirm_kill(started)
    login_as(client, killer)
    response = client.get(reverse("game:game", args=[started.code]))
    assert b"Your kills (1)" in response.content
    assert b"You're out" not in response.content


def test_game_shows_bonus_loadouts(client, started, login_as):
    player = started.players.get(name="Alice")
    assignment = player.active_assignment
    Loadout.objects.create(
        assignment=assignment,
        weapon_text="Bonus banana",
        location_text="Bonus barn",
    )

    login_as(client, player)
    response = client.get(reverse("game:game", args=[started.code]))
    assert b"Bonus banana" in response.content
    assert b"Bonus barn" in response.content


def test_game_players_dashboard_splits_alive_and_out(client, started, login_as):
    killer, victim = confirm_kill(started)
    login_as(client, killer)
    response = client.get(reverse("game:game", args=[started.code]))
    assert b"Still standing" in response.content
    assert b"Out (" in response.content


def test_new_round_excludes_previous_kills(client, started, login_as):
    killer, victim = confirm_kill(started)
    engine.reset_game(started)
    engine.start_game(started)

    login_as(client, killer)
    response = client.get(reverse("game:game", args=[started.code]))
    assert b"Your kills" in response.content
    assert b"Your kills (1)" not in response.content
    # the previous round's kill is preserved
    assert Kill.objects.filter(trip=started).count() == 1


def incoming_attempt(started):
    """Killer reports a kill on their target; the victim must respond."""
    killer = started.players.get(name="Alice")
    victim = Player.objects.get(pk=killer.active_assignment.target_id)
    attempt = engine.create_attempt(started, killer, victim)
    return killer, victim, attempt


def test_victim_sees_blocking_modal_and_no_contract(client, started, login_as):
    killer, victim, attempt = incoming_attempt(started)
    login_as(client, victim)
    response = client.get(reverse("game:game", args=[started.code]))
    assert b'class="kill-modal"' in response.content
    assert b"Yes, I'm dead" in response.content
    assert b"No, I'm alive" in response.content
    assert b"Your contract" not in response.content


def test_deny_restores_contract(client, started, login_as):
    killer, victim, attempt = incoming_attempt(started)
    engine.resolve_attempt(attempt, victim, confirmed=False)

    login_as(client, victim)
    response = client.get(reverse("game:game", args=[started.code]))
    assert b'class="kill-modal"' not in response.content
    assert b"Your contract" in response.content


def test_confirm_from_modal_kills_victim(client, started, login_as):
    killer, victim, attempt = incoming_attempt(started)
    login_as(client, victim)
    response = client.post(
        reverse("game:attempt_resolve", args=[started.code, attempt.pk, "confirm"])
    )
    assert response.status_code == 302
    response = client.get(reverse("game:game", args=[started.code]))
    assert b"You're out" in response.content


def test_report_own_death_resolves_immediately(client, started, login_as):
    victim = started.players.get(name="Alice")
    hunter = victim.assignments_received.get(is_active=True).killer
    login_as(client, victim)
    response = client.post(reverse("game:report_death", args=[started.code]))
    assert response.status_code == 302
    victim.refresh_from_db()
    assert victim.is_alive is False
    assert Kill.objects.filter(trip=started, killer=hunter, victim=victim).exists()
    assert not KillAttempt.objects.filter(
        trip=started, status=KillAttempt.Status.PENDING
    ).exists()


def test_report_button_hidden_while_kill_in_progress(client, started, login_as):
    killer, victim, attempt = incoming_attempt(started)
    login_as(client, killer)
    response = client.get(reverse("game:game", args=[started.code]))
    assert b"Your kill is in progress" in response.content
    assert b"I made the kill" not in response.content


def test_report_button_visible_without_pending(client, started, login_as):
    killer = started.players.get(name="Alice")
    login_as(client, killer)
    response = client.get(reverse("game:game", args=[started.code]))
    assert b"I made the kill" in response.content


def test_death_report_button_present_without_dialog(client, started, login_as):
    player = started.players.get(name="Alice")
    login_as(client, player)
    response = client.get(reverse("game:game", args=[started.code]))
    assert b"I got killed" in response.content
    assert b"Who killed you?" not in response.content


def test_death_report_asks_for_confirmation(client, started, login_as):
    player = started.players.get(name="Alice")
    login_as(client, player)
    response = client.get(reverse("game:game", args=[started.code]))
    assert b"Are you sure?" in response.content
    assert b'class="confirm-modal"' in response.content
    assert b"Yes, I'm out" in response.content


def test_report_death_without_contract_errors(client, trip, players, login_as):
    login_as(client, players[0])
    response = client.post(reverse("game:report_death", args=[trip.code]))
    assert response.status_code == 302
    assert not Kill.objects.filter(trip=trip).exists()
    players[0].refresh_from_db()
    assert players[0].is_alive is True
