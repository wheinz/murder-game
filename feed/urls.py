from django.urls import path

from . import views

app_name = "feed"

urlpatterns = [
    path("", views.feed, name="feed"),
    path("partials/list/", views.list_partial, name="list_partial"),
]
