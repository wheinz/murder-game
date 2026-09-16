from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("t/<str:code>/join/", views.join, name="join"),
]
