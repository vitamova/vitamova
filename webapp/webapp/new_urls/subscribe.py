from django.urls import path
from webapp.new_views.subscribe import (
    success, subscribe
)

urlpatterns = [
    path("", subscribe, name="subscribe"),
    path("success/", success, name="subscribe_success"),
    ]