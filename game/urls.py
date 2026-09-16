from django.urls import path

from . import views

app_name = "game"

urlpatterns = [
    path("", views.game, name="game"),
    path("rules/", views.rules, name="rules"),
    path("pool/", views.pool, name="pool"),
    path("attempts/new/", views.attempt_new, name="attempt_new"),
    path("reports/death/", views.report_death, name="report_death"),
    path(
        "attempts/<int:attempt_id>/<str:decision>/",
        views.attempt_resolve,
        name="attempt_resolve",
    ),
]
