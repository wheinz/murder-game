from django.urls import reverse

from core.models import Player


def test_home_renders_code_form(client):
    response = client.get(reverse("core:home"))
    assert response.status_code == 200


def test_code_gate_redirects_to_game(client, trip):
    response = client.post(reverse("core:home"), {"code": trip.code})
    assert response.status_code == 302
    assert response.url == reverse("game:game", args=[trip.code])


def test_unknown_code_shows_error(client, db):
    response = client.post(reverse("core:home"), {"code": "000000"})
    assert response.status_code == 200
    assert b"No game matches that code" in response.content


def test_invalid_code_format_shows_error(client, db):
    response = client.post(reverse("core:home"), {"code": "abc"})
    assert response.status_code == 200
    assert b"Enter the 6-digit code" in response.content


def test_join_creates_player_with_nickname(client, trip):
    response = client.post(reverse("core:join", args=[trip.code]), {"name": "Robin"})
    player = trip.players.get(name="Robin")
    assert response.status_code == 302
    assert response.url == reverse("game:game", args=[trip.code])
    assert client.session["player_id"] == player.pk


def test_nickname_must_be_unique_case_insensitive(client, trip):
    Player.objects.create(trip=trip, name="Robin")
    response = client.post(reverse("core:join", args=[trip.code]), {"name": "robin"})
    assert response.status_code == 200
    assert b"already taken" in response.content
    assert trip.players.count() == 1


def test_blank_nickname_rejected(client, trip):
    response = client.post(reverse("core:join", args=[trip.code]), {"name": "  "})
    assert response.status_code == 200
    assert trip.players.count() == 0


def test_join_assigns_four_digit_pin(client, trip):
    client.post(reverse("core:join", args=[trip.code]), {"name": "Robin"})
    player = trip.players.get(name="Robin")
    assert len(player.pin) == 4
    assert player.pin.isdigit()


def test_rejoin_with_name_and_pin_logs_back_in(client, trip):
    player = Player.objects.create(trip=trip, name="Robin", pin="1234")
    response = client.post(
        reverse("core:join", args=[trip.code]),
        {"action": "rejoin", "name": "Robin", "pin": "1234"},
    )
    assert response.status_code == 302
    assert response.url == reverse("game:game", args=[trip.code])
    assert client.session["player_id"] == player.pk
    assert trip.players.count() == 1


def test_rejoin_nickname_is_case_insensitive(client, trip):
    player = Player.objects.create(trip=trip, name="Robin", pin="1234")
    response = client.post(
        reverse("core:join", args=[trip.code]),
        {"action": "rejoin", "name": "robin", "pin": "1234"},
    )
    assert response.status_code == 302
    assert client.session["player_id"] == player.pk


def test_rejoin_with_wrong_pin_rejected(client, trip):
    Player.objects.create(trip=trip, name="Robin", pin="1234")
    response = client.post(
        reverse("core:join", args=[trip.code]),
        {"action": "rejoin", "name": "Robin", "pin": "9999"},
    )
    assert response.status_code == 200
    assert b"match anyone here" in response.content
    assert "player_id" not in client.session


def test_rejoin_with_unknown_nickname_rejected(client, trip):
    Player.objects.create(trip=trip, name="Robin", pin="1234")
    response = client.post(
        reverse("core:join", args=[trip.code]),
        {"action": "rejoin", "name": "Nobody", "pin": "1234"},
    )
    assert response.status_code == 200
    assert b"match anyone here" in response.content
    assert "player_id" not in client.session


def test_rejoin_requires_four_digit_pin(client, trip):
    Player.objects.create(trip=trip, name="Robin")
    response = client.post(
        reverse("core:join", args=[trip.code]),
        {"action": "rejoin", "name": "Robin", "pin": "12"},
    )
    assert response.status_code == 200
    assert b"4-digit player code" in response.content
    assert "player_id" not in client.session


def test_game_redirects_to_join_when_not_joined(client, trip):
    response = client.get(reverse("game:game", args=[trip.code]))
    assert response.status_code == 302
    assert response.url == reverse("core:join", args=[trip.code])


def test_joined_player_sees_game(client, trip, login_as):
    player = Player.objects.create(trip=trip, name="Robin")
    login_as(client, player)
    response = client.get(reverse("game:game", args=[trip.code]))
    assert response.status_code == 200


def test_home_sends_joined_player_to_their_game(client, trip, login_as):
    player = Player.objects.create(trip=trip, name="Robin")
    login_as(client, player)
    response = client.get(reverse("core:home"))
    assert response.status_code == 302
    assert response.url == reverse("game:game", args=[trip.code])


def test_identity_switch_and_leave_routes_removed(client, trip):
    assert client.get(f"/t/{trip.code}/switch/").status_code == 404
    assert client.get("/leave/").status_code == 404


def test_removed_players_route_is_gone(client, trip, login_as):
    player = Player.objects.create(trip=trip, name="Robin")
    login_as(client, player)
    assert client.get(f"/t/{trip.code}/players/").status_code == 404


def test_admin_is_served_at_admin(client, db):
    assert client.get("/admin/").status_code == 302
    assert client.get("/django-admin/").status_code == 404
