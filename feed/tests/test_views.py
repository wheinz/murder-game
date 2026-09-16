from django.urls import reverse

from core.models import Player
from feed.models import Post


def test_feed_post_is_not_allowed(client, trip, login_as):
    player = Player.objects.create(trip=trip, name="Robin")
    login_as(client, player)
    response = client.post(
        reverse("feed:feed", args=[trip.code]), {"body": "hello everyone"}
    )
    assert response.status_code == 405
    assert not Post.objects.filter(body="hello everyone").exists()


def test_feed_shows_system_events(client, trip):
    client.post(reverse("core:join", args=[trip.code]), {"name": "Robin"})
    response = client.get(reverse("feed:feed", args=[trip.code]))
    assert response.status_code == 200
    assert b"Robin joined the game." in response.content


def test_feed_shows_announcement(client, trip, login_as):
    player = Player.objects.create(trip=trip, name="Robin")
    login_as(client, player)
    Post.objects.create(trip=trip, body="Bring towels!", kind=Post.Kind.ANNOUNCEMENT)
    response = client.get(reverse("feed:feed", args=[trip.code]))
    assert b"Bring towels!" in response.content
    assert b"announcement" in response.content
