from django.contrib import admin, messages

from game import engine

from .models import Player, Trip


class PlayerInline(admin.TabularInline):
    model = Player
    extra = 0
    fields = ("name", "is_alive", "joined_at")
    readonly_fields = ("joined_at",)


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
    actions = ("start_game", "reset_game", "end_game")
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
    list_display = ("name", "trip", "is_alive", "joined_at")
    list_filter = ("is_alive", "trip")
    list_editable = ("is_alive",)
    search_fields = ("name",)
