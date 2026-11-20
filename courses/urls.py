from django.urls import path

from . import views

app_name = "courses"

urlpatterns = [
    path("", views.document_list, name="list"),
    path("upload/", views.document_upload, name="upload"),
    path("<int:pk>/", views.document_detail, name="detail"),
    path("<int:pk>/delete/", views.document_delete, name="delete"),
    path("<int:pk>/reprocess/", views.document_reprocess, name="reprocess"),
    path("<int:pk>/index/", views.document_index, name="index"),
    path("<int:pk>/search/", views.document_search, name="search"),
    path("<int:pk>/file/", views.document_file, name="file"),
]