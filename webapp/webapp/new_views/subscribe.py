from webapp.decorators import registered_logged_in_required, subscribed_required
from django.shortcuts import render, redirect
from django.db import connection
from django.conf import settings
from django.views.decorators.http import require_POST
import stripe
import vitalib

# Set up Stripe keys
stripe.api_key = settings.STRIPE_PRIVATE_KEY
STRIPE_PUBLIC_KEY= "pk_live_51RIChJKOiNtX3WewnOeHxiL99XltNWm2TluZew2fn6fzcmuHJ3R2x7EuLbbNpb74k1gnHlSRPHOoFJsFTEd5z8fp00rYr00NmV"

VITAMOVA_PRICE_MAP = {
    "price_1TQtOmKOiNtX3Wewk310Ygu5": "Vitamova Monthly",
    "price_1TQtPSKOiNtX3WewCEePEtQg": "Vitamova Yearly"
}

@registered_logged_in_required
def subscribe(request):

    if vitalib.User.Subscription(request.user.id, request.user.email, connection).is_active():
        return redirect("home")
    
    # Get user's score and language
    user_data = vitalib.Database.UserInfo.Get(connection, request.user.id).data()

    return render(request, "general/subscribe.html", {
        "stripe_public_key": STRIPE_PUBLIC_KEY,
        "score": vitalib.Database.UserInfo.Get(connection, request.user.id).data("vocab_score")["vocab_score"],
        "language": vitalib.Transform.Language(user_data["target_language"]).code_to_name(),
        "first_name": request.user.first_name,
    })

@require_POST
@registered_logged_in_required
def create_checkout_session(request):

    price_id = request.POST.get("price_id")

    if price_id not in VITAMOVA_PRICE_MAP:
        return redirect("/subscribe/")

    try:
        checkout_session = stripe.checkout.Session.create(
            customer_email=request.user.email,
            line_items=[
                {
                    "price": price_id,
                    "quantity": 1,
                }
            ],
            mode="subscription",
            allow_promotion_codes=True,
            payment_method_collection="if_required",
            success_url=request.build_absolute_uri("/subscribe/success/"),
            cancel_url=request.build_absolute_uri("/"),
            metadata={
                "user_id": str(request.user.id),
                "product": "vitamova",
                "price_id": price_id,
            },
            subscription_data={
                "metadata": {
                    "user_id": str(request.user.id),
                    "product": "vitamova",
                    "price_id": price_id,
                },
                "trial_period_days": 30  # 30 day free trial
            },
        )

        return redirect(checkout_session.url)

    except Exception as e:
        print(f"Error creating Stripe checkout session: {e}")
        return redirect("/subscribe/")
    
@require_POST
@registered_logged_in_required
def create_customer_portal_session(request):
    user_data = vitalib.Database.UserInfo.Get(connection, request.user.id).data(
        "stripe_customer_id"
    )

    stripe_customer_id = user_data.get("stripe_customer_id")

    if not stripe_customer_id:
        return redirect("/subscribe/")

    portal_session = stripe.billing_portal.Session.create(
        customer=stripe_customer_id,
        configuration="bpc_1TUd3xKOiNtX3WewK8WfAXcK",
        return_url=request.build_absolute_uri("/")
    )

    return redirect(portal_session.url)

@registered_logged_in_required
@subscribed_required
def success(request):
    subscribed_recently = vitalib.User.Subscription(request.user.id, request.user.email, connection).recent()
    if subscribed_recently:
        user_target_language = vitalib.Database.UserInfo.Get(connection, request.user.id).data("target_language")["target_language"]
        language_name = vitalib.Transform.Language(user_target_language).code_to_name()
        return render(request, "general/subscribe_success.html", {
            "first_name": request.user.first_name,
            "language": language_name,
        })
    else:
        return redirect("/")