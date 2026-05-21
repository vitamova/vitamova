from django.shortcuts import render, redirect
from webapp.decorators import registered_logged_in_required, subscribed_required
from django.db import connection
from django.conf import settings
from django.http import JsonResponse
import stripe
import json
import vitalib

stripe.api_key = settings.STRIPE_PRIVATE_KEY

VITAMOVA_PRICE_MAP = {
    "price_1TQtOmKOiNtX3Wewk310Ygu5": "Vitamova Monthly",
    "price_1TQtPSKOiNtX3WewCEePEtQg": "Vitamova Yearly"
}


@registered_logged_in_required
@subscribed_required
def manage(request):
    return render(request, "general/coming_soon.html", {
        "feature_name": "Manage Vocabulary",
        "message": "Manage Vocabulary is coming soon! In the meantime, you can review and practice the words you've already learned in the Review section.",
        "back_url": "/",
    })

@registered_logged_in_required
@subscribed_required
def add(request):
    if request.method == "GET":
        language = request.GET.get("language", "es")
        return render(request, "modules/vocabulary_add.html", {
            "language": language
        })
    elif request.method == "POST":
        data = json.loads(request.body)
        action = data.get("action")
        language = data.get("language")
        if action == "search_lemmas":
            query = data.get("query")
            language = data.get("language")
            lemmas = vitalib.Database.Vocab.Get(connection, request.user.id, language).lemma_starts_with(query)
            return JsonResponse(
                {
                    "status": "success",
                    "matches": lemmas
                }
            )