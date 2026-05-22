from django.urls import path
from webapp.new_views.subscribe import (
    success,
)

urlpatterns = [
    path("success/", success, name="subscribe_success"),
    ]