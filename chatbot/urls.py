from django.urls import path

from . import views

app_name = "chatbot"

urlpatterns = [
    path("", views.conversation_list, name="list"),
    path("new/", views.conversation_create, name="create"),
    path("<int:pk>/", views.conversation_detail, name="detail"),
    path("<int:pk>/send/", views.conversation_send, name="send"),
    path("<int:pk>/delete/", views.conversation_delete, name="delete"),
]