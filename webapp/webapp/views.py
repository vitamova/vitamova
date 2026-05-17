from django.shortcuts import render, redirect
from django.db import connection
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from .decorators import registered_logged_in_required
import stripe
from datetime import date
from pathlib import Path
import json
import vitalib

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

VITAMOVA_PRICE_MAP = {
    "price_1TQtOmKOiNtX3Wewk310Ygu5": "Vitamova Monthly",
    "price_1TQtPSKOiNtX3WewCEePEtQg": "Vitamova Yearly"
}

STRIPE_PUBLIC_KEY= "pk_live_51RIChJKOiNtX3WewnOeHxiL99XltNWm2TluZew2fn6fzcmuHJ3R2x7EuLbbNpb74k1gnHlSRPHOoFJsFTEd5z8fp00rYr00NmV"
# Stripe key is in data/stripe_key.txt
stripe_key_path = Path.home() / 'data' / 'stripe_key.txt'
with open(stripe_key_path, 'r') as f:
    stripe.api_key = f.read().strip()


# Define supported target languages
SUPPORTED_LANGUAGES = [
    {
        "code": "es",
        "name": "Spanish"
    },
    {
        "code": "ru",
        "name": "Russian"
    }
]

# Define supported native languages
SUPPORTED_NATIVE_LANGUAGES = [
    {
        "code": "en",
        "name": "English"
    }
]

# Get server_type from data/server_type.txt to determine if we're on prod or dev server
server_type_path = Path.home() / 'data' / 'server_type.txt'
with open(server_type_path, 'r') as f:
    server_type = f.read().strip()

# Helper functions

    
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
def home(request):

    registered_user = vitalib.Database.UserInfo.Get(connection, request.user.id).data(
        "subscribed",
        "subscription_expiration",
        "stripe_customer_id",
        "vocab_score",
        "target_language",
        "second_target_language"
        )

    subscribed, subscription_expiration, stripe_customer_id, vocab_score = (
        registered_user.get("subscribed"),
        registered_user.get("subscription_expiration"),
        registered_user.get("stripe_customer_id"),
        registered_user.get("vocab_score"),
    )

    #See if language is specified as a query parameter
    language = request.GET.get("language")

    #Get target_language value from registered_user table to pass to template
    if not language:
        language = registered_user.get("target_language", "es")

    review_count = vitalib.Database.Vocab.Get(connection, request.user.id, language).review_count()

    today = date.today()

    # If the local table says the user is unsubscribed or expired
    if not subscribed or not subscription_expiration or subscription_expiration <= today:
        # check Stripe again before showing the unsubscribed page.
        stripe_status = check_vitamova_subscription_in_stripe(request.user.email)

        subscribed = stripe_status["subscribed"]
        subscription_expiration = stripe_status["subscription_expiration"]

        vitalib.Database.UserInfo.Update(connection, request.user.id).data(
            subscribed=subscribed,
            subscription_expiration=subscription_expiration,
            stripe_customer_id=stripe_status["stripe_customer_id"]
        )

    if subscribed and subscription_expiration and subscription_expiration > today:
        return render(request, "home.html", {
            "first_name": request.user.first_name,
            "user_email": request.user.email,
            "has_score": vocab_score != -1,
            "review_count": review_count,
            "language": language,
            "language_options": vitalib.Database.UserInfo.Get(connection, request.user.id).languages(),
            "dev": server_type == 'dev'
            })

    if vocab_score == -1:
        return render(request, "home_unsubscribed_noscore.html")

    return redirect("/subscribe/")

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
        second_target_language = request.POST.get('second_target_language')
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

        # vitalib.Database.Test(connection, request.user.username, "es").score_result(data.get("answers", []))
        vitalib.Database.UserInfo.Create(connection, request.user.id).data(
            native_language=native_language,
            target_language=target_language,
            second_target_language=second_target_language,
            subscribed=subscribed,
            subscription_expiration=subscription_expiration,
            stripe_customer_id=stripe_customer_id,
        )

        return redirect('home')

    elif request.method == 'GET':
        return render(request, 'register.html', {
            'first_name': request.user.first_name,
            "native_language_options": SUPPORTED_NATIVE_LANGUAGES,
            "target_language_options": SUPPORTED_LANGUAGES
        })
    
@registered_logged_in_required
def account(request):

    if request.method == 'POST':
        example_request = {
            "first_name": "Wesley",
            "last_name": "Belleman",
            "native_language": "en",
            "target_language": "es",
            "second_target_language": "ru"
            }
        example_response = {
            "success": True,
            "message": "Account updated successfully.",
            "account": {
                "email": "wesley@example.com",
                "first_name": "Wesley",
                "last_name": "Belleman",
                "native_language": "en",
                "target_language": "es",
                "second_target_language": "ru"
            }
        }
        # We'll start with error checking. All fields are required except second_target_language
        data = json.loads(request.body.decode("utf-8"))
        first_name = data.get("first_name")
        last_name = data.get("last_name")
        native_language = data.get("native_language")
        target_language = data.get("target_language")
        second_target_language = data.get("second_target_language")
        if not first_name or not last_name or not native_language or not target_language:
            return JsonResponse({
                "success": False,
                "message": "Missing required fields."
            }, status=400)
        # target_language must be one of the codes in SUPPORTED_LANGUAGES
        if target_language not in [lang["code"] for lang in SUPPORTED_LANGUAGES]:
            return JsonResponse({
                "success": False,
                "message": "Invalid target language."
            }, status=400)
        # native_language must be one of the codes in SUPPORTED_NATIVE_LANGUAGES
        if native_language not in [lang["code"] for lang in SUPPORTED_NATIVE_LANGUAGES]:
            return JsonResponse({
                "success": False,
                "message": "Invalid native language."
            }, status=400)
        # second_target_language must be either empty or one of the codes in SUPPORTED_LANGUAGES
        if second_target_language and second_target_language not in [lang["code"] for lang in SUPPORTED_LANGUAGES]:
            return JsonResponse({
                "success": False,
                "message": "Invalid second target language."
            }, status=400)
        # Now we can update
        # Start with first_name and last_name
        request.user.first_name = first_name.strip()
        request.user.last_name = last_name.strip()
        request.user.save()
        # Now update the UserInfo table with the language preferences
        vitalib.Database.UserInfo.Update(connection, request.user.id).data(
            native_language=native_language,
            target_language=target_language,
            second_target_language=second_target_language
        )

        user_info = vitalib.Database.UserInfo.Get(connection, request.user.id).data(
            "native_language",
            "target_language",
            "second_target_language"
        )

        return JsonResponse({
            "success": True,
            "message": "Account updated successfully.",
            "account": {
                "email": request.user.email,
                "first_name": request.user.first_name,
                "last_name": request.user.last_name,
                "native_language": user_info.get("native_language"),
                "target_language": user_info.get("target_language"),
                "second_target_language": user_info.get("second_target_language")
            }
        })


    if request.method == 'GET':
        user_data = vitalib.Database.UserInfo.Get(connection, request.user.id).data(
            "native_language",
            "target_language",
            "second_target_language",
            "subscription_expiration",
        )
        return render(request, "account.html", {
            "first_name": request.user.first_name,
            "last_name": request.user.last_name,
            "user_email": request.user.email,
            "native_language": user_data.get("native_language"),
            "target_language": user_data.get("target_language"),
            "second_target_language": user_data.get("second_target_language"),
            "native_language_options": SUPPORTED_NATIVE_LANGUAGES,
            "target_language_options": SUPPORTED_LANGUAGES,
            "subscribed": is_user_subscribed(request.user),
            "subscription_expiration": user_data.get("subscription_expiration"),
        })

@registered_logged_in_required
def vocab_test(request):
    if request.method == "GET":
        language = request.GET.get("language", "es")
        vocab_score = vitalib.Database.UserInfo.Get(connection, request.user.id).score(language)
        if vocab_score == -1:
            return render(request, "vocab_test_diagnostic.html", {
                "language": language
                }
            )

        if is_user_subscribed(request.user):
            return render(request, "vocab_test_retest.html", {
                "current_score": vocab_score,
                "language": language
            })

        return redirect("/subscribe/")
    
    if request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError:
            return JsonResponse(
                {"status": "error", "message": "Invalid JSON."},
                status=400
            )
        language = data.get("language", "es")
        vocab_score = vitalib.Database.UserInfo.Get(connection, request.user.id).score(language)
        action = data.get("action")
        batch = int(data.get("batch", 1))

        # If the user is not subscribed, their score must be -1
        if not is_user_subscribed(request.user) and vocab_score != -1:
            return JsonResponse(
                {"status": "error", "message": "User must subscribe."},
                status=400
            )

        # Ensure the action is valid
        if action not in [
            "get_questions",
            "submit_batch",
            "complete_diagnostic",
            "get_retest_questions",
            "complete_retest",
            "resolve_retest_score",
        ]:
            return JsonResponse(
                {"status": "error", "message": "Invalid action."},
                status=400
            )
        
        # Set the diagnostic and retest actions

        diagnostic_actions = ["get_questions", "submit_batch", "complete_diagnostic"]
        retest_actions = ["get_retest_questions", "complete_retest", "resolve_retest_score"]

        # Let's organize by diagnostic vs retest to make the code readable
        if action in diagnostic_actions:
            # User's vocab score must be -1 to take diagnostic
            if vocab_score != -1:
                return JsonResponse(
                    {"status": "error", "message": "User has already completed diagnostic."},
                    status=400
                )
            # Implement diagnostic actions here
            if action == "get_questions":
                if batch == 1:
                    questions = vitalib.Test.Get(connection, request.user.id, language).any_questions(type="diagnostic", frontier = None, batch=1)
                elif batch in [2, 3]:
                    # The data has the answers stored as "previous_answers"
                    previous_answers = data.get("previous_answers", [])
                    frontier = vitalib.Test.Get(connection, request.user.id, language).frontier(previous_answers)
                    questions = vitalib.Test.Get(connection, request.user.id, language).any_questions(type="diagnostic", frontier=frontier, batch=batch)
                else:
                    return JsonResponse(
                        {"status": "error", "message": "Invalid batch number for action 'get_questions'."},
                        status=400
                    )
                return JsonResponse({
                    "status": "questions",
                    "batch": batch,
                    "questions": questions
                })
            if action == "submit_batch":
                # Get parameter "all_answers" from data
                all_answers = data.get("all_answers", [])
                # Get the frontier
                frontier = vitalib.Test.Get(connection, request.user.id, language).frontier(all_answers)
                # Get any_questions with type diagnostic, batch, and frontier parameters
                questions = vitalib.Test.Get(connection, request.user.id, language).any_questions(type="diagnostic", frontier=frontier, batch=batch)
                return JsonResponse({
                    "status": "questions",
                    "batch": batch+1,
                    "questions": questions
                })
            if action == "complete_diagnostic":
                if batch != 4:
                    return JsonResponse(
                        {"status": "error", "message": "Invalid batch number for action 'complete_diagnostic'."},
                        status=400
                    )
                all_answers = data.get("all_answers", [])
                # Now get an actual score based on the answers
                score = vitalib.Test.Get(connection, request.user.id, language).score_result(all_answers)
                return JsonResponse({
                    "status": "complete",
                    "score": score
                })

        if action in retest_actions:
            # User's vocab score must not be -1 to take retest
            if vocab_score == -1:
                return JsonResponse(
                    {"status": "error", "message": "User must complete diagnostic first."},
                    status=400
                )
            # Implement retest actions here
            if action == "get_retest_questions":
                pass
            if action == "complete_retest":
                pass
            if action == "resolve_retest_score":
                pass

@registered_logged_in_required
def flag_question(request):
    if request.method != "POST":
        return JsonResponse(
            {"status": "error", "message": "Invalid request method."},
            status=400
        )

    try:
        data = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse(
            {"status": "error", "message": "Invalid JSON."},
            status=400
        )

    question_id = data.get("question_id")
    language = data.get("language", "es")

    if not question_id:
        return JsonResponse(
            {"status": "error", "message": "Missing question_id."},
            status=400
        )

    flagged = vitalib.Database.Test.Questions.flag(connection, request.user.username, language, question_id)

    if flagged["status"] != "flagged":
        return JsonResponse(
            {"status": "error", "message": "Failed to flag question."},
            status=500
        )
    else:
        return JsonResponse({
            "status": "ok",
            "message": "Question flagged for review."
        })

@registered_logged_in_required
def subscribe(request):

    if is_user_subscribed(request.user):
        return redirect("home")
    
    # Get user's score and language
    user_data = vitalib.Database.UserInfo.Get(connection, request.user.id).data()

    return render(request, "subscribe.html", {
        "stripe_public_key": STRIPE_PUBLIC_KEY,
        "score": "100",
        "language": "Spanish",
        "first_name": "Wesley"
    })

@registered_logged_in_required
def vocab_builder(request):

    if not is_user_subscribed(request.user):
        return redirect("/subscribe/")
    
    if request.method == "GET":
        language = request.GET.get("language", "es")
        return render(request, "vocab_builder.html", {
            "language": language
        })
    if request.method == "POST":
        # Get the data
        data = json.loads(request.body.decode("utf-8"))
        # Get language from data
        language = data.get("language", "es")
        action = data.get("action")
        if action == "load_questions":
            score = vitalib.Database.UserInfo.Get(connection, request.user.id).score(language)
            questions = vitalib.Test.Get(connection, request.user.id, language).new_questions("vocab_builder", score)
            return JsonResponse({
                "status": "ok",
                "questions": questions
            })
        if action == "submit_answers":
            pass

@registered_logged_in_required
def review(request):

    if not is_user_subscribed(request.user):
        return redirect("/subscribe/")

    return render(request, "coming_soon.html", {
        "feature_name": "Review",
        "message": "Review is coming soon! In the meantime, you can practice the words you've already learned in the Reading Practice section.",
        "back_url": "/",
    })

@registered_logged_in_required
def reading_practice(request):

    if not is_user_subscribed(request.user):
        return redirect("/subscribe/")

    return render(request, "coming_soon.html", {
        "feature_name": "Reading Practice",
        "message": "Reading Practice is coming soon! In the meantime, you can review and practice the words you've already learned in the Review section.",
        "back_url": "/",
    })