import pytest
from django.conf import settings
from django.contrib.sessions.backends.db import SessionStore

from core.models import Player, Trip


@pytest.fixture(autouse=True)
def _plain_staticfiles(settings):
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


@pytest.fixture
def trip(db):
    return Trip.objects.create(name="Test Trip")


@pytest.fixture
def players(trip):
    names = ["Alice", "Bob", "Cara", "Dan"]
    return [Player.objects.create(trip=trip, name=name) for name in names]


@pytest.fixture
def login_as(db):
    def _login(client, player):
        session = SessionStore()
        session["player_id"] = player.pk
        session.create()
        client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key

    return _login
