from django.contrib import admin
from django.urls import include, path

from core import views as core_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("courses/", include("courses.urls")),
    path("", core_views.dashboard, name="dashboard"),
    path("summaries/", include("summaries.urls")),
    path("quizzes/", include("quizzes.urls")),
    path("chatbot/", include("chatbot.urls")),
]
# Les fichiers importés (MEDIA_ROOT) ne sont JAMAIS servis directement, même en DEBUG :
# ils passent par la vue courses:file, qui vérifie que l'utilisateur en est le propriétaire.