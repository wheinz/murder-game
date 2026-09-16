from django.db import models
from django.utils import timezone

from core.models import Player, Trip


class Post(models.Model):
    class Kind(models.TextChoices):
        SYSTEM = "system", "System"
        ANNOUNCEMENT = "announcement", "Announcement"

    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="posts")
    author = models.ForeignKey(
        Player, null=True, blank=True, on_delete=models.SET_NULL, related_name="posts"
    )
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.SYSTEM)
    body = models.TextField()
    is_pinned = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-is_pinned", "-created_at"]

    def __str__(self):
        return self.body[:60]

    @classmethod
    def system(cls, trip, body, author=None):
        return cls.objects.create(trip=trip, body=body, author=author, kind=cls.Kind.SYSTEM)
