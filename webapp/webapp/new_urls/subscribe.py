from django.urls import path
from webapp.new_views.subscribe import (
    success, subscribe, create_checkout_session, create_customer_portal_session
)

urlpatterns = [
    path("", subscribe, name="subscribe"),
    path("create-checkout-session/", create_checkout_session, name="create_checkout_session"),
    path("create-customer-portal-session/", create_customer_portal_session, name="create_customer_portal_session"),
    path("success/", success, name="subscribe_success"),
    ]