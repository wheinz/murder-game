from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("t/<str:code>/", include("game.urls")),
    path("t/<str:code>/feed/", include("feed.urls")),
    path("t/<str:code>/gallery/", include("gallery.urls")),
    path("", include("core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
