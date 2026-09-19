from django.contrib import admin, messages
from django.urls import reverse
from django.utils.html import format_html

from game import engine

from .models import Player, Trip


class PlayerInline(admin.TabularInline):
    model = Player
    extra = 0
    fields = ("name", "pin", "is_alive", "joined_at")
    readonly_fields = ("pin", "joined_at")


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "game_status",
        "game_number",
        "player_count",
        "starts_on",
    )
    list_filter = ("game_status",)
    search_fields = ("name", "code")
    inlines = [PlayerInline]
    actions = ("start_game", "grant_bonus", "reset_game", "end_game")
    fieldsets = (
        (None, {"fields": ("name", "code", "game_status")}),
        ("Dates", {"fields": ("starts_on", "ends_on")}),
    )

    @admin.display(description="players")
    def player_count(self, obj):
        return obj.players.count()

    @admin.action(description="Start the hunt")
    def start_game(self, request, queryset):
        for trip in queryset:
            try:
                engine.start_game(trip)
            except engine.GameError as exc:
                self.message_user(request, f"{trip.name}: {exc}", messages.ERROR)
            else:
                self.message_user(request, f"{trip.name}: hunt started.", messages.SUCCESS)

    @admin.action(description="Grant bonus weapon & location")
    def grant_bonus(self, request, queryset):
        for trip in queryset:
            try:
                engine.grant_bonus(trip)
            except engine.GameError as exc:
                self.message_user(request, f"{trip.name}: {exc}", messages.ERROR)
            else:
                self.message_user(request, f"{trip.name}: bonus granted.", messages.SUCCESS)

    @admin.action(description="Reset the game to setup")
    def reset_game(self, request, queryset):
        for trip in queryset:
            engine.reset_game(trip)
        self.message_user(request, "Selected trips reset to setup.", messages.SUCCESS)

    @admin.action(description="End the hunt now")
    def end_game(self, request, queryset):
        for trip in queryset:
            engine.end_game(trip)
        self.message_user(request, "Selected trips ended.", messages.SUCCESS)


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ("name", "pin", "trip", "is_alive", "login_as", "joined_at")
    list_filter = ("is_alive", "trip")
    list_editable = ("is_alive",)
    search_fields = ("name", "pin")
    readonly_fields = ("pin",)

    @admin.display(description="")
    def login_as(self, obj):
        url = reverse("core:impersonate", args=[obj.pk])
        return format_html('<a class="button" href="{}">Log in as</a>', url)
