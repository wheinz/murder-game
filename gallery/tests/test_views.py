import io
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from core.models import Player
from gallery.models import Photo


@pytest.fixture(autouse=True)
def _media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


def make_image():
    buffer = io.BytesIO()
    Image.new("RGB", (12, 12), "red").save(buffer, "PNG")
    return SimpleUploadedFile("test.png", buffer.getvalue(), content_type="image/png")


def test_photo_upload(client, trip, login_as):
    player = Player.objects.create(trip=trip, name="Robin")
    login_as(client, player)
    response = client.post(
        reverse("gallery:gallery", args=[trip.code]),
        {"image": make_image(), "caption": "Sunset"},
    )
    assert response.status_code == 302
    photo = trip.photos.get()
    assert photo.caption == "Sunset"
    assert photo.uploaded_by_id == player.pk


def test_gallery_page_renders(client, trip, login_as):
    player = Player.objects.create(trip=trip, name="Robin")
    login_as(client, player)
    response = client.get(reverse("gallery:gallery", args=[trip.code]))
    assert response.status_code == 200


def test_gallery_page_has_no_delete_button(client, trip, login_as):
    player = Player.objects.create(trip=trip, name="Robin")
    login_as(client, player)
    response = client.get(reverse("gallery:gallery", args=[trip.code]))
    assert b"Delete" not in response.content


def test_photo_delete_route_removed(client, trip, login_as):
    player = Player.objects.create(trip=trip, name="Robin")
    login_as(client, player)
    response = client.get(f"/t/{trip.code}/gallery/photos/1/delete/")
    assert response.status_code == 404


def test_photo_file_removed_on_queryset_delete(client, trip, login_as):
    player = Player.objects.create(trip=trip, name="Robin")
    login_as(client, player)
    client.post(reverse("gallery:gallery", args=[trip.code]), {"image": make_image()})
    photo = trip.photos.get()
    path = Path(photo.image.path)
    assert path.exists()

    Photo.objects.all().delete()

    assert not trip.photos.exists()
    assert not path.exists()
