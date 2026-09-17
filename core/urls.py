from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("t/<str:code>/join/", views.join, name="join"),
    path("impersonate/<int:player_id>/", views.impersonate, name="impersonate"),
    path("impersonate/stop/", views.stop_impersonating, name="stop_impersonate"),
]
