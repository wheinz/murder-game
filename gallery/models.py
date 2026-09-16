import uuid
from pathlib import Path

from django.db import models
from django.utils import timezone

from core.models import Player, Trip


def photo_upload_to(instance, filename):
    suffix = Path(filename).suffix.lower() or ".jpg"
    return f"trips/{instance.trip.code}/{uuid.uuid4().hex}{suffix}"


class Photo(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="photos")
    uploaded_by = models.ForeignKey(
        Player, null=True, blank=True, on_delete=models.SET_NULL, related_name="photos"
    )
    image = models.ImageField(upload_to=photo_upload_to)
    caption = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.caption or f"Photo {self.pk}"
