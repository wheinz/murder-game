from django.db import models
from django.utils import timezone

from core.models import Player, Trip


class PoolItem(models.Model):
    """Shared base for weapons and locations submitted to a trip's pool."""

    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="%(class)ss")
    text = models.CharField(max_length=120)
    submitted_by = models.ForeignKey(
        Player,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(class)ss",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        ordering = ["text"]

    def __str__(self):
        return self.text


class Weapon(PoolItem):
    class Meta:
        ordering = ["text"]
        constraints = [
            models.UniqueConstraint(fields=["trip", "text"], name="unique_weapon_per_trip")
        ]


class Location(PoolItem):
    class Meta:
        ordering = ["text"]
        constraints = [
            models.UniqueConstraint(
                fields=["trip", "text"], name="unique_location_per_trip"
            )
        ]


class Assignment(models.Model):
    """An active contract: killer hunts target using weapon_text at location_text."""

    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="assignments")
    killer = models.ForeignKey(
        Player, on_delete=models.CASCADE, related_name="assignments_given"
    )
    target = models.ForeignKey(
        Player, on_delete=models.CASCADE, related_name="assignments_received"
    )
    weapon_text = models.CharField(max_length=120)
    location_text = models.CharField(max_length=120)
    game_number = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.killer} → {self.target} ({self.weapon_text})"

    def close(self):
        self.is_active = False
        self.ended_at = timezone.now()
        self.save(update_fields=["is_active", "ended_at"])


class Loadout(models.Model):
    """An extra weapon/location pair granted to a contract as a bonus."""

    assignment = models.ForeignKey(
        Assignment, on_delete=models.CASCADE, related_name="loadouts"
    )
    weapon_text = models.CharField(max_length=120)
    location_text = models.CharField(max_length=120)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at", "pk"]

    def __str__(self):
        return f"{self.weapon_text} at {self.location_text}"


class KillAttempt(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        DENIED = "denied", "Denied"

    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="kill_attempts")
    killer = models.ForeignKey(
        Player, on_delete=models.CASCADE, related_name="attempts_as_killer"
    )
    victim = models.ForeignKey(
        Player, on_delete=models.CASCADE, related_name="attempts_as_victim"
    )
    initiated_by = models.ForeignKey(
        Player, on_delete=models.CASCADE, related_name="attempts_initiated"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    weapon_text = models.CharField(max_length=120, blank=True)
    location_text = models.CharField(max_length=120, blank=True)
    game_number = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.killer} vs {self.victim} ({self.status})"

    @property
    def awaiting(self):
        """The party who still needs to act on a pending attempt."""
        return self.victim if self.initiated_by_id == self.killer_id else self.killer


class Kill(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="kills")
    killer = models.ForeignKey(
        Player, on_delete=models.CASCADE, related_name="kills_as_killer"
    )
    victim = models.ForeignKey(
        Player, on_delete=models.CASCADE, related_name="kills_as_victim"
    )
    weapon_text = models.CharField(max_length=120)
    location_text = models.CharField(max_length=120)
    game_number = models.PositiveIntegerField(default=0)
    confirmed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-confirmed_at"]

    def __str__(self):
        return f"{self.killer} killed {self.victim}"
