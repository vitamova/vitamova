from django.urls import path
from webapp.new_views.labs import (
    writing
)

urlpatterns = [
    path("writing/", writing, name="writing_lab")
]