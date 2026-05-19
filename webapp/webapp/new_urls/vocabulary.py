from django.urls import path
from webapp.new_views.vocabulary import (
    add,
    manage
)

urlpatterns = [
    path("add/", add, name="vocabulary_add"),
    path("manage/", manage, name="vocabulary_manage"),
]