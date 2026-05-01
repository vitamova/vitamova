from django.shortcuts import render, redirect
from django.db import connection
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.http import JsonResponse
import stripe
from datetime import date
from pathlib import Path
import json
import random

from openai import OpenAI

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

    if not is_registered_user(request.user):
        return redirect("/register/")

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

        if batch == "1":
            fetch_counts = {
                1: 3,
                2: 3,
                3: 3,
                4: 3,
                5: 3,
                6: 3,
            }

        elif batch in ["2", "3", "4"]:
            level_correct_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}
            level_total_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}

            with connection.cursor() as cursor:
                for answer in all_answers:
                    question_id = answer.get("question_id")
                    selected_option = answer.get("selected_option")

                    if not question_id or not selected_option:
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

                    for lvl, (min_rank, max_rank) in level_ranges.items():
                        if max_rank is None:
                            if lemma_rank >= min_rank:
                                level = lvl
                                break
                        elif min_rank <= lemma_rank <= max_rank:
                            level = lvl
                            break

                    if not level:
                        continue

                    if selected_option.strip().casefold() == correct_answer.strip().casefold():
                        level_correct_counts[level] += 1

                    level_total_counts[level] += 1

                frontier_level = 1

            for lvl in range(1, 7):
                total = level_total_counts[lvl]
                correct = level_correct_counts[lvl]

                # If this level has not been tested yet, do not use it as the frontier.
                if total == 0:
                    continue

                accuracy = correct / total

                # The first level below 80% becomes the frontier.
                # This guarantees that all earlier tested levels were 80% or higher,
                # because otherwise the loop would have stopped earlier.
                if accuracy < 0.8:
                    frontier_level = lvl
                    break
            else:
                # If every tested level was 80% or higher, focus on the highest level.
                frontier_level = 6

            # If this is the last submission
            if action == "complete_diagnostic":
                level_correct_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}
                level_total_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}

                level_weighted_correct = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0, 6: 0.0}
                level_weighted_total = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0, 6: 0.0}

                above_frontier_weighted_correct = 0.0
                above_frontier_weighted_total = 0.0

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

                        for lvl, (min_rank, max_rank) in level_ranges.items():
                            if max_rank is None:
                                if lemma_rank >= min_rank:
                                    level = lvl
                                    min_rank_for_level = min_rank
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
                        # Easier/earlier words in the level are worth about 1.0.
                        # Harder/later words in the level are worth up to about 2.0.
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

                # Find the first level below 80%.
                # All previous tested levels must be 80%+ because the loop stops at the first miss of that threshold.
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

                # Base score is 1,000 points for every fully mastered level below the frontier.
                base_score = 1000 * (frontier_level - 1)

                # Raw bonus is based on rank-weighted accuracy inside the frontier level.
                # 40% = bottom of the band, 80% = top of the band.
                frontier_weighted_total = level_weighted_total[frontier_level]
                frontier_weighted_correct = level_weighted_correct[frontier_level]

                if frontier_weighted_total > 0:
                    frontier_weighted_accuracy = frontier_weighted_correct / frontier_weighted_total
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

                # Now calculate the confidence multiplier from ALL levels above the frontier.
                # Correct answers farther above the frontier count more.
                # Harder lemma ranks inside each upper level also count more.
                for lvl in range(frontier_level + 1, 7):
                    level_distance = lvl - frontier_level

                    # Level distance makes higher levels worth more.
                    # frontier + 1 = 1.0x
                    # frontier + 2 = 1.5x
                    # frontier + 3 = 2.0x
                    # etc.
                    distance_weight = 1.0 + (0.5 * (level_distance - 1))

                    above_frontier_weighted_correct += (
                        level_weighted_correct[lvl] * distance_weight
                    )
                    above_frontier_weighted_total += (
                        level_weighted_total[lvl] * distance_weight
                    )

                if above_frontier_weighted_total > 0:
                    above_frontier_accuracy = (
                        above_frontier_weighted_correct / above_frontier_weighted_total
                    )
                else:
                    above_frontier_accuracy = 0.0

                # Confidence is limited if we barely sampled above the frontier.
                # 12 weighted attempts is treated as enough evidence for full confidence.
                sample_confidence = min(1.0, above_frontier_weighted_total / 12.0)

                # Proof score combines correctness and sample size.
                above_frontier_proof = above_frontier_accuracy * sample_confidence

                # Multiplier ranges from 0.70 to 1.00.
                # No higher-level proof still allows 70% of the raw bonus.
                # Strong higher-level proof allows the full raw bonus.
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
            
            elif action == "submit_batch":
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
                    {"status": "error", "message": "Invalid batch."},
                    status=400
                )

        with connection.cursor() as cursor:
            for level, (min_rank, max_rank) in level_ranges.items():
                count = fetch_counts.get(level, 0)

                if count <= 0:
                    continue

                if max_rank is None:
                    cursor.execute(
                        """
                        SELECT id,
                            question,
                            correct_answer,
                            distractor_1,
                            distractor_2,
                            distractor_3
                        FROM spanish_vocab_test_bank
                        WHERE lemma_rank >= %s
                        ORDER BY RANDOM()
                        LIMIT %s
                        """,
                        [min_rank, count]
                    )
                else:
                    cursor.execute(
                        """
                        SELECT id,
                            question,
                            correct_answer,
                            distractor_1,
                            distractor_2,
                            distractor_3
                        FROM spanish_vocab_test_bank
                        WHERE lemma_rank BETWEEN %s AND %s
                        ORDER BY RANDOM()
                        LIMIT %s
                        """,
                        [min_rank, max_rank, count]
                    )

                rows = cursor.fetchall()

                for row in rows:
                    options = [
                        row[2],
                        row[3],
                        row[4],
                        row[5],
                    ]

                    random.shuffle(options)

                    questions.append({
                        "question_id": row[0],
                        "question": row[1],
                        "options": options,
                    })

        return JsonResponse({
            "status": "questions",
            "questions": questions
        })

    # Users with no vocab score can always take the free diagnostic,
    # regardless of subscription status.
    if vocab_score == -1:
        return render(request, "vocab_test_diagnostic.html")

    if is_user_subscribed(request.user):
        return render(request, "vocab_test_retake.html")

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

    return render(request, "subscribe.html", {
        "stripe_public_key": STRIPE_PUBLIC_KEY
    })