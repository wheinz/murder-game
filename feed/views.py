from django.shortcuts import render
from django.views.decorators.http import require_GET

from core.auth import player_required

from .models import Post


def _feed_context(request):
    return {
        "trip": request.trip,
        "posts": Post.objects.filter(trip=request.trip).select_related("author"),
    }


@require_GET
@player_required
def feed(request, code):
    return render(request, "feed/feed.html", _feed_context(request))


@player_required
def list_partial(request, code):
    return render(request, "feed/partials/list.html", _feed_context(request))
