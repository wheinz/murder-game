import secrets

from django.db import models
from django.utils import timezone


def generate_code():
    """A 6-digit numeric entry code, unique across trips."""
    while True:
        code = f"{secrets.randbelow(1_000_000):06d}"
        if not Trip.objects.filter(code=code).exists():
            return code


class Trip(models.Model):
    class GameStatus(models.TextChoices):
        SETUP = "setup", "Setup"
        ACTIVE = "active", "Active"
        FINISHED = "finished", "Finished"

    name = models.CharField(max_length=120)
    code = models.CharField(max_length=6, unique=True, default=generate_code)
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    game_status = models.CharField(
        max_length=16, choices=GameStatus.choices, default=GameStatus.SETUP
    )
    game_number = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "game"
        verbose_name_plural = "games"

    def __str__(self):
        return self.name

    @property
    def alive_players(self):
        return self.players.filter(is_alive=True)

    @property
    def winner(self):
        if self.game_status != self.GameStatus.FINISHED:
            return None
        return self.players.filter(is_alive=True).first()

    def date_range_display(self):
        if self.starts_on and self.ends_on:
            if self.starts_on == self.ends_on:
                return self.starts_on.strftime("%d %b %Y")
            return f"{self.starts_on:%d %b} – {self.ends_on:%d %b %Y}"
        if self.starts_on:
            return self.starts_on.strftime("%d %b %Y")
        return ""


class Player(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="players")
    name = models.CharField(max_length=80)
    is_alive = models.BooleanField(default=True)
    joined_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["trip", "name"], name="unique_player_name"),
        ]

    def __str__(self):
        return self.name

    @property
    def active_assignment(self):
        return self.assignments_given.filter(is_active=True).first()
