from django.shortcuts import render, redirect
from django.db import connection
import stripe
from datetime import date
from pathlib import Path

VITAMOVA_PRICE_MAP = {
    # Replace this with your real Stripe monthly price ID
    "price_1TQtOmKOiNtX3Wewk310Ygu5": "Vitamova Monthly",
    "price_1TQtPSKOiNtX3WewCEePEtQg": "Vitamova Yearly"
}

# Stripe key is in data/stripe_key.txt
stripe_key_path = Path.home() / 'data' / 'stripe_key.txt'
with open(stripe_key_path, 'r') as f:
    stripe.api_key = f.read().strip()

def check_vitamova_subscription_in_stripe(user_email):
    subscribed = False
    subscription_expiration = None
    stripe_customer_id = None
    subscription_id = None

    customers = stripe.Customer.list(
        email=user_email,
        limit=10
    ).data

    for customer in customers:
        subscriptions = stripe.Subscription.list(
            customer=customer.id,
            status="all",
            limit=100
        ).data

        for sub in subscriptions:
            if sub.status not in ["active", "trialing"]:
                continue

            items = sub["items"]["data"]

            for item in items:
                price_id = item["price"]["id"]

                # Only count Vitamova subscriptions
                # This prevents another Evenstar product from granting Vitamova access.
                if price_id in VITAMOVA_PRICE_MAP:
                    subscribed = True
                    stripe_customer_id = customer.id
                    subscription_id = sub.id

                    if sub.current_period_end:
                        subscription_expiration = date.fromtimestamp(
                            sub.current_period_end
                        )

                    return {
                        "subscribed": subscribed,
                        "subscription_expiration": subscription_expiration,
                        "stripe_customer_id": stripe_customer_id,
                        "subscription_id": subscription_id,
                    }

    return {
        "subscribed": subscribed,
        "subscription_expiration": subscription_expiration,
        "stripe_customer_id": stripe_customer_id,
        "subscription_id": subscription_id,
    }


def home(request):
    if not request.user.is_authenticated:
        return redirect("login")

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT subscribed, subscription_expiration, stripe_customer_id
            FROM registered_user
            WHERE user_id = %s
            LIMIT 1
            """,
            [request.user.id]
        )
        registered_user = cursor.fetchone()

    if not registered_user:
        return redirect("/register/")

    subscribed = registered_user[0]
    subscription_expiration = registered_user[1]
    stripe_customer_id = registered_user[2]

    today = date.today()

    if subscribed and subscription_expiration and subscription_expiration > today:
        return render(request, "home.html")

    # If the local table says the user is unsubscribed or expired,
    # check Stripe again before showing the unsubscribed page.
    stripe_status = check_vitamova_subscription_in_stripe(request.user.email)

    subscribed = stripe_status["subscribed"]
    subscription_expiration = stripe_status["subscription_expiration"]
    stripe_customer_id = stripe_status["stripe_customer_id"]

    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE registered_user
            SET subscribed = %s,
                subscription_expiration = %s,
                stripe_customer_id = COALESCE(%s, stripe_customer_id)
            WHERE user_id = %s
            """,
            [
                subscribed,
                subscription_expiration,
                stripe_customer_id,
                request.user.id,
            ]
        )

    if subscribed and subscription_expiration and subscription_expiration > today:
        return render(request, "home.html")

    return render(request, "home_unsubscribed.html")

def login(request):
    return render(request, 'login.html')

def register(request):
    if not request.user.is_authenticated:
        return redirect('login')

    if request.method == 'POST':
        native_language = request.POST.get('native_language')
        target_language = request.POST.get('target_language')
        agree_terms = request.POST.get('agree_terms')

        if not agree_terms:
            return render(request, 'register.html', {
                'first_name': request.user.first_name,
                'error': 'You must agree to the Terms and Conditions to continue.'
            })

        subscribed = False
        subscription_expiration = None
        stripe_customer_id = None
        vitamova_subscription_id = None

        customers = stripe.Customer.list(
            email=request.user.email,
            limit=10
        ).data

        for customer in customers:
            subscriptions = stripe.Subscription.list(
                customer=customer.id,
                status='all',
                limit=100
            ).data

            for sub in subscriptions:
                # Only count active/trialing subscriptions as subscribed.
                # You can add "past_due" here later if you want to keep access
                # during failed payment recovery.
                if sub.status not in ["active", "trialing"]:
                    continue

                items = sub["items"]["data"]

                for item in items:
                    price_id = item["price"]["id"]

                    if price_id in VITAMOVA_PRICE_MAP:
                        subscribed = True
                        stripe_customer_id = customer.id
                        vitamova_subscription_id = sub.id

                        if sub.current_period_end:
                            subscription_expiration = date.fromtimestamp(
                                sub.current_period_end
                            )

                        break

                if subscribed:
                    break

            if subscribed:
                break

        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO registered_user (
                    user_id,
                    native_language,
                    target_language,
                    vocab_score,
                    subscribed,
                    subscription_expiration,
                    stripe_customer_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id)
                DO UPDATE SET
                    native_language = EXCLUDED.native_language,
                    target_language = EXCLUDED.target_language,
                    subscribed = EXCLUDED.subscribed,
                    subscription_expiration = EXCLUDED.subscription_expiration,
                    stripe_customer_id = EXCLUDED.stripe_customer_id
                """,
                [
                    request.user.id,
                    native_language,
                    target_language,
                    0,
                    subscribed,
                    subscription_expiration,
                    stripe_customer_id,
                ]
            )

        return redirect('home')

    elif request.method == 'GET':
        return render(request, 'register.html', {
            'first_name': request.user.first_name
        })