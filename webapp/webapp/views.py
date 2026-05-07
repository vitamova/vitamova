from django.shortcuts import render, redirect
from django.db import connection
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.http import JsonResponse
from .decorators import registered_subscribed_required
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

    #See if language is specified as a query parameter
    target_language = request.GET.get("language")

    #Get target_language value from registered_user table to pass to template
    if not target_language:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT target_language
                FROM registered_user
                WHERE user_id = %s
                LIMIT 1
                """,
                [request.user.id]
            )
            target_language_row = cursor.fetchone()
            target_language = target_language_row[0] if target_language_row else None

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM user_vocabulary
            WHERE user_id = %s
            AND language = %s
            AND next_review_at IS NOT NULL
            AND next_review_at < %s
            """,
            [
                request.user.id,
                target_language,
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
            "review_count": review_count,
            "language": target_language,
            "language_options": [
                {"code": "ru", "name": "Russian"},
                {"code": "es", "name": "Spanish"}
                ]
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
            "review_count": review_count,
            "language": target_language,
            "language_options": [
                {"code": "es", "name": "Spanish"},
                ]
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

        # vitalib.Test(connection, request.user.username, "es").score_result(data.get("answers", []))
        vitalib.UserInfo.Create(connection, request.user.id).data(
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


def vocab_test(request):
    if not request.user.is_authenticated:
        return redirect("login")

    if not is_registered_user(request.user):
        return redirect("/register/")

    # Get the user's current vocab score once.
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT vocab_score
            FROM registered_user
            WHERE user_id = %s
            LIMIT 1
            """,
            [request.user.id]
        )
        row = cursor.fetchone()

    vocab_score = row[0]
    # If the score is not -1 calculate the frontier
    if vocab_score != -1:
        frontier = (vocab_score // 1000) + 1
        frontier = max(1, min(6, frontier))

    # -------------------------------------------------------------------------
    # POST requests are used by the diagnostic/retest frontend XHR flows.
    # -------------------------------------------------------------------------
    if request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError:
            return JsonResponse(
                {"status": "error", "message": "Invalid JSON."},
                status=400
            )

        action = data.get("action")
        batch = str(data.get("batch", "1"))
        all_answers = data.get("all_answers", [])

        questions = []

        level_ranges = {
            1: (1, 1500),
            2: (1501, 3000),
            3: (3001, 6000),
            4: (6001, 10000),
            5: (10001, 15000),
            6: (15001, None),
        }

        # ---------------------------------------------------------------------
        # RETEST ACTION PLACEHOLDERS
        #
        # These should probably stay near the top of the POST block because they
        # are separate flows from the initial diagnostic.
        # ---------------------------------------------------------------------

        retest_actions = [ "get_retest_questions", "complete_retest", "resolve_retest_score" ]

        if action in retest_actions:
            #If the user's score is -1 return an error
            if vocab_score == -1:
                return JsonResponse(
                    {"status": "error", "message": "No existing score found for retest."},
                    status=400
                )
            language = data.get("language", "es")

            if action == "get_retest_questions":
                fetch_counts = {
                    1: 0,
                    2: 0,
                    3: 0,
                    4: 0,
                    5: 0,
                    6: 0,
                }
                # If the frontier is 2, 3, 4, or 5, 30 questions from the frontier and 10 from the level below.
                if frontier in [2, 3, 4, 5]:
                    fetch_counts[frontier] = 30
                    fetch_counts[frontier - 1] = 10
                    fetch_counts[frontier + 1] = 10
                # If the frontier is 1, 35 questions from level 1 and 15 from level 2.
                elif frontier == 1:
                    fetch_counts[1] = 35
                    fetch_counts[2] = 15
                # If the frontier is 6, 35 questions from level 6 and 15 from level 5.
                elif frontier == 6:
                    fetch_counts[6] = 35
                    fetch_counts[5] = 15
                questions = vitalib.Test(connection, request.user.username, language).get_questions(fetch_counts)
                return JsonResponse({
                    "status": "questions",
                    "questions": questions,
                })
                

            elif action == "complete_retest":
                example_request = {
                    "action": "complete_retest",
                    "current_score": 2730,
                    "current_frontier": 3,
                    "answers": [
                        {
                        "question_id": 123,
                        "selected_option": "varias"
                        }
                    ],
                    "total_questions": 50,
                    "language": "es"
                    }
                example_response = {
                    "status": "complete",
                    "outcome": "improved",
                    "current_score": 2730,
                    "new_score": 3120,
                    "frontier_accuracy": 0.83,
                    "below_frontier_accuracy": 0.90,
                    "above_frontier_accuracy": 0.40
                    }
                score_result = vitalib.Test(connection, request.user.username, language).score_result(data.get("answers", []))
                if score_result["score"] > vocab_score:
                    outcome = "improved"
                elif score_result["score"] <= vocab_score:
                    # If frontier accuracy was less than 0.35 and below frontier acccuracy was less than 0.7
                    # We outcome is downgrade_choice
                    # Otherwise outcome is keep_current
                    if score_result["frontier_accuracy"] < 0.35 and score_result["below_frontier_accuracy"] < 0.7:
                        outcome = "downgrade_choice"
                    else:
                        outcome = "keep_current"
                return JsonResponse({
                    "status": "complete",
                    "outcome": outcome,
                    "current_score": vocab_score,
                    "new_score": score_result["score"],
                    "frontier_accuracy": score_result["frontier_accuracy"],
                    "below_frontier_accuracy": score_result["below_frontier_accuracy"],
                    "above_frontier_accuracy": score_result["above_frontier_accuracy"],
                })

            elif action == "resolve_retest_score":
                example_request = {
                    "action": "resolve_retest_score",
                    "choice": "keep_current",
                    "current_score": 2730,
                    "new_score": 1720,
                    "language": "es"
                    }
                example_response = {
                    "status": "ok"
                    }
                # Choice options are keep_current or accept_new
                choice = data.get("choice")
                # Keep_current is easy - just return ok without changing anything
                if choice == "keep_current":
                    return JsonResponse({
                        "status": "ok"
                    })
                # Accept_new means we want to update the user's score to the new score calculated in complete_retest
                # Use the db helper function to update the user's score in the database
                elif choice == "accept_new":
                    vitalib.UserInfo.Update(connection, request.user.id).score(language, data.get("new_score"))
                    updated_score = vitalib.UserInfo.Get(connection, request.user.id).score()
                    if updated_score != data.get("new_score"):
                        return JsonResponse({
                            "status": "error",
                            "message": "Failed to update score."
                        }, status=500)
                    else:
                        return JsonResponse({
                            "status": "ok"
                        })
            # ---------------------------------------------------------------------
            # DIAGNOSTIC ACTIONS
            #
            # Existing supported actions:
            # - get_questions
            # - submit_batch
            # - complete_diagnostic
            # ---------------------------------------------------------------------

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

        # ---------------------------------------------------------------------
        # Diagnostic batch 1:
        # Broad scan, 3 questions from each level.
        # ---------------------------------------------------------------------
        if action == "get_questions" and batch == "1":
            fetch_counts = {
                1: 3,
                2: 3,
                3: 3,
                4: 3,
                5: 3,
                6: 3,
            }

        # ---------------------------------------------------------------------
        # Diagnostic batches 2-4:
        # Score all previous answers and use the frontier level to select the
        # next adaptive question distribution, or calculate the final score.
        # ---------------------------------------------------------------------
        elif action in ["submit_batch", "complete_diagnostic"] and batch in ["1", "2", "3", "4"]:
            level_correct_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}
            level_total_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}

            level_weighted_correct = {
                1: 0.0,
                2: 0.0,
                3: 0.0,
                4: 0.0,
                5: 0.0,
                6: 0.0,
            }

            level_weighted_total = {
                1: 0.0,
                2: 0.0,
                3: 0.0,
                4: 0.0,
                5: 0.0,
                6: 0.0,
            }

            # Score all submitted answers so far.
            with connection.cursor() as cursor:
                for answer in all_answers:
                    question_id = answer.get("question_id")
                    selected_option = answer.get("selected_option")

                    if not question_id or selected_option is None:
                        continue

                    cursor.execute(
                        """
                        SELECT correct_answer, lemma_rank
                        FROM spanish_vocab_test_bank
                        WHERE id = %s
                        """,
                        [question_id]
                    )
                    row = cursor.fetchone()

                    if not row:
                        continue

                    correct_answer = row[0]
                    lemma_rank = row[1]

                    level = None
                    min_rank_for_level = None
                    max_rank_for_level = None

                    # Determine level from lemma_rank.
                    for lvl, (min_rank, max_rank) in level_ranges.items():
                        if max_rank is None:
                            if lemma_rank >= min_rank:
                                level = lvl
                                min_rank_for_level = min_rank

                                # Level 6 has no natural upper bound in level_ranges.
                                # This synthetic bound is only for rank weighting.
                                max_rank_for_level = min_rank + 5000
                                break

                        elif min_rank <= lemma_rank <= max_rank:
                            level = lvl
                            min_rank_for_level = min_rank
                            max_rank_for_level = max_rank
                            break

                    if not level:
                        continue

                    is_correct = (
                        str(selected_option).strip().casefold()
                        == str(correct_answer).strip().casefold()
                    )

                    level_total_counts[level] += 1

                    if is_correct:
                        level_correct_counts[level] += 1

                    # Rank weight within the level.
                    # Earlier/easier words are around 1.0.
                    # Later/harder words are up to around 2.0.
                    level_span = max_rank_for_level - min_rank_for_level

                    if level_span <= 0:
                        rank_position = 0.0
                    else:
                        rank_position = (lemma_rank - min_rank_for_level) / level_span
                        rank_position = max(0.0, min(1.0, rank_position))

                    rank_weight = 1.0 + rank_position

                    level_weighted_total[level] += rank_weight

                    if is_correct:
                        level_weighted_correct[level] += rank_weight

            # Find the first tested level below 80%.
            # Since the loop stops there, all earlier tested levels were 80%+.
            frontier_level = 1

            for lvl in range(1, 7):
                total = level_total_counts[lvl]
                correct = level_correct_counts[lvl]

                if total == 0:
                    continue

                accuracy = correct / total

                if accuracy < 0.8:
                    frontier_level = lvl
                    break
            else:
                frontier_level = 6

            # -----------------------------------------------------------------
            # Final diagnostic submission:
            # Calculate score and update vocab_score.
            # -----------------------------------------------------------------
            if action == "complete_diagnostic":
                base_score = 1000 * (frontier_level - 1)

                frontier_weighted_total = level_weighted_total[frontier_level]
                frontier_weighted_correct = level_weighted_correct[frontier_level]

                if frontier_weighted_total > 0:
                    frontier_weighted_accuracy = (
                        frontier_weighted_correct / frontier_weighted_total
                    )
                else:
                    frontier_weighted_accuracy = 0.0

                entry_threshold = 0.40
                mastery_threshold = 0.80

                raw_bonus_progress = (
                    (frontier_weighted_accuracy - entry_threshold)
                    / (mastery_threshold - entry_threshold)
                )
                raw_bonus_progress = max(0.0, min(1.0, raw_bonus_progress))

                raw_bonus = round(999 * raw_bonus_progress)

                above_frontier_weighted_correct = 0.0
                above_frontier_weighted_total = 0.0

                # Confidence multiplier from all levels above the frontier.
                # Higher levels and harder ranks count more.
                for lvl in range(frontier_level + 1, 7):
                    level_distance = lvl - frontier_level

                    # frontier + 1 = 1.0x
                    # frontier + 2 = 1.5x
                    # frontier + 3 = 2.0x
                    distance_weight = 1.0 + (0.5 * (level_distance - 1))

                    above_frontier_weighted_correct += (
                        level_weighted_correct[lvl] * distance_weight
                    )
                    above_frontier_weighted_total += (
                        level_weighted_total[lvl] * distance_weight
                    )

                if above_frontier_weighted_total > 0:
                    above_frontier_accuracy = (
                        above_frontier_weighted_correct
                        / above_frontier_weighted_total
                    )
                else:
                    above_frontier_accuracy = 0.0

                # Sample confidence prevents tiny above-frontier samples from
                # over-influencing the multiplier.
                sample_confidence = min(1.0, above_frontier_weighted_total / 12.0)

                above_frontier_proof = above_frontier_accuracy * sample_confidence

                # Multiplier range: 0.70 to 1.00.
                confidence_multiplier = 0.70 + (0.30 * above_frontier_proof)

                bonus = round(raw_bonus * confidence_multiplier)

                score = base_score + bonus
                score = max(0, min(6000, score))

                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE registered_user
                        SET vocab_score = %s
                        WHERE user_id = %s
                        """,
                        [score, request.user.id]
                    )

                return JsonResponse({
                    "status": "complete",
                    "score": score,
                    "frontier_level": frontier_level,
                    "base_score": base_score,
                    "raw_bonus": raw_bonus,
                    "confidence_multiplier": round(confidence_multiplier, 3),
                    "bonus": bonus
                })

            # -----------------------------------------------------------------
            # Intermediate diagnostic submission:
            # Use the frontier level to choose the next adaptive batch.
            # -----------------------------------------------------------------
            if action == "submit_batch":
                if frontier_level == 1:
                    fetch_counts = {
                        1: 12,
                        2: 6,
                        3: 0,
                        4: 0,
                        5: 0,
                        6: 0,
                    }

                elif frontier_level == 6:
                    fetch_counts = {
                        1: 0,
                        2: 0,
                        3: 0,
                        4: 0,
                        5: 6,
                        6: 12,
                    }

                else:
                    fetch_counts = {
                        1: 0,
                        2: 0,
                        3: 0,
                        4: 0,
                        5: 0,
                        6: 0,
                    }
                    fetch_counts[frontier_level] = 10
                    fetch_counts[frontier_level - 1] = 4
                    fetch_counts[frontier_level + 1] = 4

        else:
            return JsonResponse(
                {"status": "error", "message": "Invalid diagnostic request."},
                status=400
            )

        # ---------------------------------------------------------------------
        # Fetch diagnostic questions based on fetch_counts.
        # ---------------------------------------------------------------------
        language = data.get("language", "es")
        questions = vitalib.Test(connection, request.user.username, language).get_questions(fetch_counts)

        return JsonResponse({
            "status": "questions",
            "questions": questions
        })

    # -------------------------------------------------------------------------
    # GET request page rendering
    # -------------------------------------------------------------------------

    # Users with no vocab score can always take the free diagnostic,
    # regardless of subscription status.
    if vocab_score == -1:
        return render(request, "vocab_test_diagnostic.html")

    if is_user_subscribed(request.user):
        return render(request, "vocab_test_retest.html", {
            "current_score": vocab_score
        })

    return redirect("/subscribe/")

def flag_question(request):
    if request.method != "POST":
        return JsonResponse(
            {"status": "error", "message": "Invalid request method."},
            status=400
        )

    if not request.user.is_authenticated:
        return JsonResponse(
            {"status": "error", "message": "User not authenticated."},
            status=401
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

    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO flagged_questions (
                user_id,
                question_id,
                language,
                flagged_at
            )
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id, question_id, language)
            DO UPDATE SET flagged_at = EXCLUDED.flagged_at
            """,
            [
                request.user.id,
                question_id,
                language,
                timezone.now()
            ]
        )

    return JsonResponse({
        "status": "ok",
        "message": "Question flagged for review."
    })

def subscribe(request):
    if not request.user.is_authenticated:
        return redirect("login")

    if not is_registered_user(request.user):
        return redirect("/register/")

    if is_user_subscribed(request.user):
        return redirect("home")
    
    # Get user's score and language
    user_data = vitalib.UserInfo.Get(connection, request.user.id).data()

    return render(request, "subscribe.html", {
        "stripe_public_key": STRIPE_PUBLIC_KEY,
        "score": "100",
        "language": "Spanish",
        "first_name": "Wesley"
    })

@registered_subscribed_required
def vocab_builder(request):
    if not request.user.is_authenticated:
        return redirect("login")

    if not is_registered_user(request.user):
        return redirect("/register/")

    if not is_user_subscribed(request.user):
        return redirect("/subscribe/")

    return render(request, "coming_soon.html", {
        "feature_name": "Vocab Builder",
        "message": "Vocab Builder is coming soon! In the meantime, you can review and practice the words you've already learned in the Review and Reading Practice sections.",
        "back_url": "/",
    })

@registered_subscribed_required
def review(request):
    if not request.user.is_authenticated:
        return redirect("login")

    if not is_user_subscribed(request.user):
        return redirect("/subscribe/")

    return render(request, "coming_soon.html", {
        "feature_name": "Review",
        "message": "Review is coming soon! In the meantime, you can practice the words you've already learned in the Reading Practice section.",
        "back_url": "/",
    })

@registered_subscribed_required
def reading_practice(request):
    if not request.user.is_authenticated:
        return redirect("/login/")

    if not is_user_subscribed(request.user):
        return redirect("/subscribe/")

    return render(request, "coming_soon.html", {
        "feature_name": "Reading Practice",
        "message": "Reading Practice is coming soon! In the meantime, you can review and practice the words you've already learned in the Review section.",
        "back_url": "/",
    })