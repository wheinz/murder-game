import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from core.models import Player
from game import engine
from game.models import Kill, KillAttempt, Location, Weapon


@pytest.fixture
def started(trip, players):
    for i in range(len(players)):
        Weapon.objects.create(trip=trip, text=f"Weapon {i}")
        Location.objects.create(trip=trip, text=f"Place {i}")
    engine.start_game(trip)
    return trip


@pytest.fixture
def admin_client(client, db):
    user = get_user_model().objects.create_superuser("op", "op@example.com", "pw")
    client.force_login(user)
    return client


def make_attempt(trip, killer_name="Alice"):
    killer = trip.players.get(name=killer_name)
    victim = Player.objects.get(pk=killer.active_assignment.target_id)
    return engine.create_attempt(trip, killer, victim)


def run_action(client, attempt, action):
    return client.post(
        reverse("admin:game_killattempt_changelist"),
        {
            "action": action,
            "select_across": "0",
            "index": "0",
            "_selected_action": [str(attempt.pk)],
        },
    )


def test_admin_confirm_action_inherits_contract(admin_client, started):
    attempt = make_attempt(started)
    killer = attempt.killer
    victim = attempt.victim
    victim_contract = victim.active_assignment

    response = run_action(admin_client, attempt, "confirm_kills")
    assert response.status_code == 302

    attempt.refresh_from_db()
    victim.refresh_from_db()
    assert attempt.status == KillAttempt.Status.CONFIRMED
    assert victim.is_alive is False

    new_contract = killer.assignments_given.get(is_active=True)
    assert new_contract.target_id == victim_contract.target_id
    assert new_contract.weapon_text == victim_contract.weapon_text
    assert new_contract.location_text == victim_contract.location_text
    assert Kill.objects.filter(trip=started, killer=killer, victim=victim).exists()


def test_admin_deny_action_leaves_game_unchanged(admin_client, started):
    attempt = make_attempt(started)
    killer = attempt.killer
    victim = attempt.victim

    response = run_action(admin_client, attempt, "deny_kills")
    assert response.status_code == 302

    attempt.refresh_from_db()
    victim.refresh_from_db()
    assert attempt.status == KillAttempt.Status.DENIED
    assert victim.is_alive is True
    assert killer.assignments_given.get(is_active=True).target_id == victim.pk
    assert not Kill.objects.filter(trip=started).exists()


def test_admin_confirm_reports_stale_attempt(admin_client, started):
    attempt = make_attempt(started)
    run_action(admin_client, attempt, "confirm_kills")
    response = run_action(admin_client, attempt, "confirm_kills")

    assert response.status_code == 302
    assert Kill.objects.filter(trip=started).count() == 1
