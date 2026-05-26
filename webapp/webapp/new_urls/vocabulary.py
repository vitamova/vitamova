from django.urls import path
from webapp.new_views.vocabulary import (
    add,
    manage,
    build,
    review
)

urlpatterns = [
    path("add/", add, name="vocabulary_add"),
    path("manage/", manage, name="vocabulary_manage"),
    path("build/", build, name="vocabulary_build"),
    path("review/", review, name="vocabulary_review"),
]