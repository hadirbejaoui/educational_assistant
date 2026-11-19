from django.urls import path

from . import views

app_name = "quizzes"

urlpatterns = [
    path("", views.quiz_list, name="list"),
    path("create/", views.quiz_create, name="create"),
    path("<int:pk>/", views.quiz_detail, name="detail"),
    path("<int:pk>/take/", views.quiz_take, name="take"),
    path("<int:pk>/delete/", views.quiz_delete, name="delete"),
    path("attempts/<int:pk>/", views.attempt_result, name="result"),
]