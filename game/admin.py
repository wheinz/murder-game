from django.contrib import admin, messages

from . import engine
from .models import Assignment, Kill, KillAttempt, Location, Weapon


@admin.register(Weapon)
class WeaponAdmin(admin.ModelAdmin):
    list_display = ("text", "trip", "submitted_by", "is_active")


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("text", "trip", "submitted_by", "is_active")


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "killer",
        "target",
        "weapon_text",
        "location_text",
        "is_active",
        "game_number",
    )
    list_filter = ("is_active", "game_number")


@admin.register(KillAttempt)
class KillAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "killer",
        "victim",
        "status",
        "initiated_by",
        "game_number",
        "created_at",
    )
    list_filter = ("status", "game_number")
    list_select_related = ("killer", "victim", "initiated_by")
    actions = ("confirm_kills", "deny_kills")

    @admin.action(description="Confirm selected kills")
    def confirm_kills(self, request, queryset):
        self._resolve(request, queryset, confirmed=True)

    @admin.action(description="Deny selected kills")
    def deny_kills(self, request, queryset):
        self._resolve(request, queryset, confirmed=False)

    def _resolve(self, request, queryset, confirmed):
        resolved = 0
        for attempt in queryset:
            try:
                engine.resolve_attempt(attempt, attempt.awaiting, confirmed=confirmed)
            except engine.GameError as exc:
                self.message_user(request, f"{attempt}: {exc}", messages.ERROR)
            else:
                resolved += 1
        if resolved:
            verb = "confirmed" if confirmed else "denied"
            self.message_user(
                request, f"{resolved} kill report(s) {verb}.", messages.SUCCESS
            )


@admin.register(Kill)
class KillAdmin(admin.ModelAdmin):
    list_display = (
        "killer",
        "victim",
        "weapon_text",
        "location_text",
        "game_number",
        "confirmed_at",
    )
    list_filter = ("game_number",)
