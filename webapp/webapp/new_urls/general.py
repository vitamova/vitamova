from django.urls import path
from webapp.new_views.general import prepare

urlpatterns = [
    path("prepare/", prepare, name="general_prepare"),
    # Add more general URLs here as needed
    ]