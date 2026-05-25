from django.urls import path
from webapp.new_views.general import prepare, register_success


urlpatterns = [
    path("prepare/", prepare, name="general_prepare"),
    path("register-success/", register_success, name="register_success"),
    # Add more general URLs here as needed
    ]