from django.urls import path

from . import views

app_name = "summaries"

urlpatterns = [
    path("", views.summary_list, name="list"),
    path("document/<int:pk>/", views.document_summaries, name="document"),
    path(
        "document/<int:pk>/generate/<str:level>/",
        views.summary_generate,
        name="generate",
    ),
]