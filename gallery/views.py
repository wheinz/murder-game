from django.contrib import messages
from django.shortcuts import redirect, render

from core.auth import player_required
from feed.models import Post

from .forms import PhotoForm


def _gallery_context(request):
    return {
        "trip": request.trip,
        "photos": request.trip.photos.select_related("uploaded_by"),
        "form": PhotoForm(),
    }


@player_required
def gallery(request, code):
    if request.method == "POST":
        form = PhotoForm(request.POST, request.FILES)
        if form.is_valid():
            photo = form.save(commit=False)
            photo.trip = request.trip
            photo.uploaded_by = request.current_player
            photo.save()
            Post.system(
                request.trip,
                f"{request.current_player.name} added a photo.",
                author=request.current_player,
            )
            messages.success(request, "Photo added.")
        else:
            for error in form.errors.get("image", []):
                messages.error(request, error)
        if request.headers.get("HX-Request"):
            context = _gallery_context(request)
            return render(request, "gallery/partials/grid.html", context)
        return redirect("gallery:gallery", code=code)

    return render(request, "gallery/gallery.html", _gallery_context(request))
