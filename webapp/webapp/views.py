from django.shortcuts import render, redirect
from django.db import connection
from django.views.decorators.http import require_POST
from django.utils import timezone
import stripe
from datetime import date
from pathlib import Path

VITAMOVA_PRICE_MAP = {
    "price_1TQtOmKOiNtX3Wewk310Ygu5": "Vitamova Monthly",
    "price_1TQtPSKOiNtX3WewCEePEtQg": "Vitamova Yearly"
}

STRIPE_PUBLIC_KEY= "pk_live_51RIChJKOiNtX3WewnOeHxiL99XltNWm2TluZew2fn6fzcmuHJ3R2x7EuLbbNpb74k1gnHlSRPHOoFJsFTEd5z8fp00rYr00NmV"
# Stripe key is in data/stripe_key.txt
stripe_key_path = Path.home() / 'data' / 'stripe_key.txt'
with open(stripe_key_path, 'r') as f:
    stripe.api_key = f.read().strip()

# Helper functions

def is_registered_user(user):
    if not user or not user.is_authenticated:
        return False

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1
            FROM registered_user
            WHERE user_id = %s
            LIMIT 1
            """,
            [user.id]
        )
        return cursor.fetchone() is not None
    
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
        customer_id = customer.get("id")

        if not customer_id:
            continue

        subscriptions = stripe.Subscription.list(
            customer=customer_id,
            status="all",
            limit=100
        ).data

        for sub in subscriptions:
            sub_status = sub.get("status")

            if sub_status not in ["active", "trialing"]:
                continue

            items = sub.get("items", {}).get("data", [])

            for item in items:
                price_id = item.get("price", {}).get("id")

                # Only count Vitamova subscriptions.
                # This prevents another Evenstar product from granting Vitamova access.
                if price_id in VITAMOVA_PRICE_MAP:
                    subscribed = True
                    stripe_customer_id = customer_id
                    subscription_id = sub.get("id")
                    current_period_end = sub.get("current_period_end")

                    if not current_period_end:
                        items = sub.get("items", {}).get("data", [])
                        if items:
                            current_period_end = items[0].get("current_period_end")

                    if current_period_end:
                        subscription_expiration = date.fromtimestamp(current_period_end)

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

def is_user_subscribed(user, check_stripe_if_stale=True):
    if not user or not user.is_authenticated:
        return False

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT subscribed, subscription_expiration
            FROM registered_user
            WHERE user_id = %s
            LIMIT 1
            """,
            [user.id]
        )
        row = cursor.fetchone()

    if not row:
        return False

    subscribed = row[0]
    subscription_expiration = row[1]
    today = date.today()

    if subscribed and subscription_expiration and subscription_expiration > today:
        return True

    if not check_stripe_if_stale:
        return False

    stripe_status = check_vitamova_subscription_in_stripe(user.email)

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
                user.id,
            ]
        )

    return bool(
        subscribed
        and subscription_expiration
        and subscription_expiration > today
    )

# Views
    
@require_POST
def create_checkout_session(request):
    if not request.user.is_authenticated:
        return redirect("login")

    if not is_registered_user(request.user):
        return redirect("/register/")

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
            success_url=request.build_absolute_uri("/"),
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
                }
            },
        )

        return redirect(checkout_session.url)

    except Exception as e:
        print(f"Error creating Stripe checkout session: {e}")
        return redirect("/subscribe/")


def home(request):
    if not request.user.is_authenticated:
        return redirect("login")

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT subscribed, subscription_expiration, stripe_customer_id, vocab_score
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
    vocab_score = registered_user[3]

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM user_vocabulary
            WHERE user_id = %s
            AND next_review_at IS NOT NULL
            AND next_review_at < %s
            """,
            [
                request.user.id,
                timezone.now(),
            ]
        )
    review_count = cursor.fetchone()[0]

    today = date.today()

    if subscribed and subscription_expiration and subscription_expiration > today:
        return render(request, "home.html", {
            "first_name": request.user.first_name,
            "user_email": request.user.email,
            "has_score": vocab_score != -1,
            "review_count": review_count
            })

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
        return render(request, "home.html", {
            "first_name": request.user.first_name,
            "user_email": request.user.email,
            "has_score": vocab_score != -1,
            "review_count": review_count
            })

    if vocab_score == -1:
        return render(request, "home_unsubscribed_noscore.html")

    return render(request, "home_unsubscribed.html")

def login(request):
    if request.user.is_authenticated:
        return redirect('home')
    else:
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

        stripe_status = check_vitamova_subscription_in_stripe(request.user.email)

        subscribed = stripe_status["subscribed"]
        subscription_expiration = stripe_status["subscription_expiration"]
        stripe_customer_id = stripe_status["stripe_customer_id"]

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
                    -1,
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
    
def vocab_test(request):
    if not request.user.is_authenticated:
        return redirect("login")

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT subscribed, subscription_expiration, stripe_customer_id, vocab_score
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
    vocab_score = registered_user[3]

    today = date.today()

    has_current_subscription = (
        subscribed
        and subscription_expiration
        and subscription_expiration > today
    )

    # Let users take the vocab test for free if they have not been assessed yet.
    if has_current_subscription or vocab_score == -1:
        return render(request, "vocab_test.html")

    # Local DB says they are not currently subscribed and they already have a score,
    # so check Stripe one more time before redirecting them to subscribe.
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

    has_current_subscription = (
        subscribed
        and subscription_expiration
        and subscription_expiration > today
    )

    if has_current_subscription or vocab_score == -1:
        return render(request, "vocab_test.html")

    return redirect("/subscribe/")

def subscribe(request):
    if not request.user.is_authenticated:
        return redirect("login")

    if not is_registered_user(request.user):
        return redirect("/register/")

    if is_user_subscribed(request.user):
        return redirect("home")

    return render(request, "subscribe.html", {
        "stripe_public_key": STRIPE_PUBLIC_KEY
    })