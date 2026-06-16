from django.urls import path
from webapp.new_views.labs import (
    writing,
    speaking
)

urlpatterns = [
    path("writing/", writing, name="writing_lab"),
    path("speaking/", speaking, name="speaking_lab")
]