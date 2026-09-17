from .auth import get_current_player, get_impersonated_player


def current_player(request):
    player = getattr(request, "current_player", None)
    if player is None:
        player = get_current_player(request)
    return {
        "current_player": player,
        "impersonating": get_impersonated_player(request),
    }
