import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from core.auth import IMPERSONATE_KEY


@pytest.fixture
def staff_client(client, db):
    user = get_user_model().objects.create_user("op", "op@example.com", "pw", is_staff=True)
    client.force_login(user)
    return client


def test_staff_can_impersonate_player_and_lands_on_game(staff_client, trip, players):
    target = players[0]
    response = staff_client.get(reverse("core:impersonate", args=[target.pk]))

    assert response.status_code == 302
    assert response.url == reverse("game:game", args=[trip.code])
    assert staff_client.session[IMPERSONATE_KEY] == target.pk

    page = staff_client.get(reverse("game:game", args=[trip.code]))
    assert page.status_code == 200
    assert target.name.encode() in page.content


def test_exit_stops_impersonation(staff_client, trip, players):
    target = players[0]
    staff_client.get(reverse("core:impersonate", args=[target.pk]))

    response = staff_client.get(reverse("core:stop_impersonate"))

    assert response.status_code == 302
    assert response.url == reverse("admin:index")
    assert IMPERSONATE_KEY not in staff_client.session


def test_impersonation_does_not_clobber_own_player_session(staff_client, trip, players):
    own, target = players[0], players[1]
    session = staff_client.session
    session["player_id"] = own.pk
    session.save()

    staff_client.get(reverse("core:impersonate", args=[target.pk]))
    page = staff_client.get(reverse("game:game", args=[trip.code]))
    assert target.name.encode() in page.content

    staff_client.get(reverse("core:stop_impersonate"))
    assert staff_client.session["player_id"] == own.pk
    page = staff_client.get(reverse("game:game", args=[trip.code]))
    assert own.name.encode() in page.content


def test_non_staff_cannot_impersonate(client, trip, players):
    target = players[0]
    response = client.get(reverse("core:impersonate", args=[target.pk]))

    assert response.status_code == 302
    assert "/admin/login/" in response.url
    assert IMPERSONATE_KEY not in client.session


def test_non_staff_user_cannot_impersonate(client, db, trip, players):
    user = get_user_model().objects.create_user("regular", "r@example.com", "pw")
    client.force_login(user)

    response = client.get(reverse("core:impersonate", args=[players[0].pk]))

    assert response.status_code == 302
    assert "/admin/login/" in response.url
    assert IMPERSONATE_KEY not in client.session


def test_banner_shows_only_while_impersonating(staff_client, trip, players):
    target = players[0]
    game_url = reverse("game:game", args=[trip.code])
    exit_url = reverse("core:stop_impersonate")

    assert b"Viewing as" not in staff_client.get(game_url).content

    staff_client.get(reverse("core:impersonate", args=[target.pk]))
    content = staff_client.get(game_url).content
    assert b"Viewing as" in content
    assert exit_url.encode() in content
