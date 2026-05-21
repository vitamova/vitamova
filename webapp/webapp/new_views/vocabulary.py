from django.shortcuts import render, redirect
from webapp.decorators import registered_logged_in_required, subscribed_required
from django.db import connection
from datetime import date
import stripe
from django.conf import settings

stripe.api_key = settings.STRIPE_PRIVATE_KEY

VITAMOVA_PRICE_MAP = {
    "price_1TQtOmKOiNtX3Wewk310Ygu5": "Vitamova Monthly",
    "price_1TQtPSKOiNtX3WewCEePEtQg": "Vitamova Yearly"
}


@registered_logged_in_required
@subscribed_required
def manage(request):
    if not is_user_subscribed(request.user):
        return redirect("/subscribe/")

    return render(request, "general/coming_soon.html", {
        "feature_name": "Manage Vocabulary",
        "message": "Manage Vocabulary is coming soon! In the meantime, you can review and practice the words you've already learned in the Review section.",
        "back_url": "/",
    })

@registered_logged_in_required
@subscribed_required
def add(request):
    if not is_user_subscribed(request.user):
        return redirect("/subscribe/")

    return render(request, "general/coming_soon.html", {
        "feature_name": "Add Vocabulary",
        "message": "Add Vocabulary is coming soon! In the meantime, you can review and practice the words you've already learned in the Review section.",
        "back_url": "/",
    })