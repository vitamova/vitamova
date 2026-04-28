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

openai_key_path = Path.home() / 'data' / 'chatgpt_key.txt'
with open(openai_key_path, 'r') as f:
    OPENAI_KEY = f.read().strip()

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


DIAGNOSTIC_MODEL = "gpt-5-mini"

QUESTIONS_PER_BATCH = 18
TOTAL_BATCHES = 4
TOTAL_QUESTIONS = QUESTIONS_PER_BATCH * TOTAL_BATCHES

ENTRY_THRESHOLD = 0.40
MASTERY_THRESHOLD = 0.80
BAND_SIZE = 1000
MAX_SCORE = 6000

LEVEL_RANGES = {
    1: (1, 1500),
    2: (1501, 3000),
    3: (3001, 6000),
    4: (6001, 10000),
    5: (10001, 15000),
    6: (15001, None),
}


def get_level_for_rank(rank):
    for level, (min_rank, max_rank) in LEVEL_RANGES.items():
        if max_rank is None:
            if rank >= min_rank:
                return level
        elif min_rank <= rank <= max_rank:
            return level

    return 6


def normalize_answer(value):
    if value is None:
        return ""

    return str(value).strip().casefold()


def get_initial_level_counts():
    return {
        1: 3,
        2: 3,
        3: 3,
        4: 3,
        5: 3,
        6: 3,
    }


def get_neighbor_counts(frontier, mode):
    """
    Returns 18 total questions.

    mode:
    - "expand": candidate frontier expansion
    - "focus": score refinement
    - "confirm": final confirmation
    """

    if frontier <= 1:
        return {1: 9, 2: 9}

    if frontier >= 6:
        return {5: 9, 6: 9}

    if mode == "expand":
        return {
            frontier - 1: 6,
            frontier: 6,
            frontier + 1: 6,
        }

    if mode == "focus":
        return {
            frontier - 1: 4,
            frontier: 8,
            frontier + 1: 6,
        }

    if mode == "confirm":
        return {
            frontier - 1: 2,
            frontier: 8,
            frontier + 1: 8,
        }

    return {
        frontier - 1: 6,
        frontier: 6,
        frontier + 1: 6,
    }


def score_submitted_answers(all_answers):
    """
    all_answers format:
    [
        {
            "question_id": 123,
            "selected_option": "house"
        }
    ]

    Returns:
    {
        1: {"correct": 2, "total": 3},
        ...
    }
    """

    results = {
        level: {"correct": 0, "total": 0}
        for level in range(1, 7)
    }

    if not all_answers:
        return results

    question_ids = []

    for answer in all_answers:
        question_id = answer.get("question_id")

        if question_id is not None:
            question_ids.append(int(question_id))

    if not question_ids:
        return results

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT id, lemma_rank, correct_answer
            FROM spanish_vocab_test_bank
            WHERE id = ANY(%s)
            """,
            [question_ids]
        )
        rows = cursor.fetchall()

    question_lookup = {}

    for question_id, lemma_rank, correct_answer in rows:
        question_lookup[question_id] = {
            "lemma_rank": lemma_rank,
            "correct_answer": correct_answer,
            "level": get_level_for_rank(lemma_rank),
        }

    for answer in all_answers:
        question_id = answer.get("question_id")
        selected_option = answer.get("selected_option")

        if question_id is None:
            continue

        question_id = int(question_id)

        if question_id not in question_lookup:
            continue

        question_data = question_lookup[question_id]
        level = question_data["level"]

        results[level]["total"] += 1

        if normalize_answer(selected_option) == normalize_answer(question_data["correct_answer"]):
            results[level]["correct"] += 1

    return results


def get_accuracy_by_level(level_results):
    accuracies = {}

    for level in range(1, 7):
        correct = level_results[level]["correct"]
        total = level_results[level]["total"]

        if total == 0:
            accuracies[level] = 0.0
        else:
            accuracies[level] = correct / total

    return accuracies


def find_candidate_frontier_after_initial_scan(level_results):
    """
    After the first broad scan, find the first range where the user missed anything.
    If they missed nothing, assume top range.
    """

    for level in range(1, 7):
        total = level_results[level]["total"]
        correct = level_results[level]["correct"]

        if total > 0 and correct < total:
            return level

    return 6


def find_frontier(level_results):
    """
    Finds the first level below mastery.
    """

    accuracies = get_accuracy_by_level(level_results)

    for level in range(1, 7):
        if accuracies[level] < MASTERY_THRESHOLD:
            return level

    return 6


def choose_level_counts_for_next_batch(all_answers, next_batch):
    """
    Batch 1:
      3 questions from each range.

    Batch 2:
      Candidate frontier expansion.

    Batch 3:
      Focus around frontier.

    Batch 4:
      Confirm frontier and next range.
    """

    if next_batch == 1:
        return get_initial_level_counts()

    level_results = score_submitted_answers(all_answers)

    if next_batch == 2:
        candidate_frontier = find_candidate_frontier_after_initial_scan(level_results)
        return get_neighbor_counts(candidate_frontier, "expand")

    frontier = find_frontier(level_results)

    if next_batch == 3:
        return get_neighbor_counts(frontier, "focus")

    return get_neighbor_counts(frontier, "confirm")


def calculate_frontier_score(all_answers):
    """
    Frontier-gated score out of 6,000.

    Logic:
    - Each level is a 1,000-point band.
    - ENTRY_THRESHOLD means the user is entering that band.
    - MASTERY_THRESHOLD means they are near the top of that band.
    - If the next band is below entry threshold, the user does not cross into it.
    """

    level_results = score_submitted_answers(all_answers)
    accuracies = get_accuracy_by_level(level_results)

    frontier = None

    for level in range(1, 7):
        if accuracies[level] < MASTERY_THRESHOLD:
            frontier = level
            break

    if frontier is None:
        return MAX_SCORE

    frontier_accuracy = accuracies[frontier]

    # If the user has not entered this range, cap them near the top of the previous band.
    if frontier_accuracy < ENTRY_THRESHOLD:
        if frontier == 1:
            return 0

        return ((frontier - 1) * BAND_SIZE) - 50

    band_min = (frontier - 1) * BAND_SIZE
    band_max = frontier * BAND_SIZE

    progress = (frontier_accuracy - ENTRY_THRESHOLD) / (MASTERY_THRESHOLD - ENTRY_THRESHOLD)
    progress = max(0, min(1, progress))

    score = round(band_min + (progress * BAND_SIZE))

    # Avoid showing a perfect band score unless they actually cross into the next band.
    if score >= band_max and frontier < 6:
        score = band_max - 50

    return max(0, min(MAX_SCORE, score))


def fetch_existing_questions_for_level(level, count, used_question_ids):
    min_rank, max_rank = LEVEL_RANGES[level]

    used_question_ids = used_question_ids or []

    if max_rank is None:
        rank_clause = "lemma_rank >= %s"
        params = [min_rank]
    else:
        rank_clause = "lemma_rank BETWEEN %s AND %s"
        params = [min_rank, max_rank]

    used_clause = ""

    if used_question_ids:
        used_clause = "AND id <> ALL(%s)"
        params.append(used_question_ids)

    params.append(count)

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT id, question, correct_answer, distractor_1, distractor_2, distractor_3
            FROM spanish_vocab_test_bank
            WHERE {rank_clause}
              {used_clause}
            ORDER BY RANDOM()
            LIMIT %s
            """,
            params
        )
        return cursor.fetchall()


def fetch_lemmas_for_question_generation(level, count):
    min_rank, max_rank = LEVEL_RANGES[level]

    if max_rank is None:
        rank_clause = "sl.rank >= %s"
        params = [min_rank, count]
    else:
        rank_clause = "sl.rank BETWEEN %s AND %s"
        params = [min_rank, max_rank, count]

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT sl.rank, sl.lemma, sl.pos, sl.translation, sl.definition
            FROM spanish_lemmas sl
            WHERE {rank_clause}
              AND NOT EXISTS (
                  SELECT 1
                  FROM spanish_vocab_test_bank q
                  WHERE q.lemma_rank = sl.rank
              )
            ORDER BY RANDOM()
            LIMIT %s
            """,
            params
        )
        rows = cursor.fetchall()

    # If every lemma in this range already has a generated question,
    # fall back to any lemma in the range.
    if rows:
        return rows

    if max_rank is None:
        params = [min_rank, count]
    else:
        params = [min_rank, max_rank, count]

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT sl.rank, sl.lemma, sl.pos, sl.translation, sl.definition
            FROM spanish_lemmas sl
            WHERE {rank_clause}
            ORDER BY RANDOM()
            LIMIT %s
            """,
            params
        )
        return cursor.fetchall()


def generate_questions_with_openai(lemma_rows):
    #Create the client
    OPENAI_CLIENT = OpenAI(api_key=OPENAI_KEY)
    """
    lemma_rows:
    [
        (rank, lemma, pos, translation, definition)
    ]

    Returns:
    [
        {
            "lemma_rank": 123,
            "question": "...",
            "correct_answer": "...",
            "distractor_1": "...",
            "distractor_2": "...",
            "distractor_3": "..."
        }
    ]
    """

    if not lemma_rows:
        return []

    input_items = []

    for rank, lemma, pos, translation, definition in lemma_rows:
        input_items.append({
            "lemma_rank": rank,
            "lemma": lemma,
            "part_of_speech": pos,
            "translation": translation,
            "definition_es": definition,
        })

    prompt = f"""
You are creating multiple-choice Spanish vocabulary diagnostic questions.

For each Spanish lemma, create one question.

Question style:
- Ask for the best English meaning of the Spanish lemma.
- Keep the question short.
- Use the lemma and part of speech to disambiguate meaning.
- The correct_answer must be the best concise English answer.
- The distractors must be plausible but clearly wrong.
- Avoid making distractors that are just spelling variants or near-identical synonyms.
- Avoid making every distractor an obvious joke answer.
- If the lemma is a cognate, make the distractors strong enough that the question is still meaningful.
- Return only valid JSON.

Input lemmas:
{json.dumps(input_items, ensure_ascii=False)}
"""

    response = OPENAI_CLIENT.responses.create(
        model=DIAGNOSTIC_MODEL,
        input=prompt,
        text={
            "format": {
                "type": "json_schema",
                "name": "vocab_diagnostic_questions",
                "schema": {
                    "type": "object",
                    "properties": {
                        "results": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "lemma_rank": {"type": "integer"},
                                    "question": {"type": "string"},
                                    "correct_answer": {"type": "string"},
                                    "distractor_1": {"type": "string"},
                                    "distractor_2": {"type": "string"},
                                    "distractor_3": {"type": "string"}
                                },
                                "required": [
                                    "lemma_rank",
                                    "question",
                                    "correct_answer",
                                    "distractor_1",
                                    "distractor_2",
                                    "distractor_3"
                                ],
                                "additionalProperties": False
                            }
                        }
                    },
                    "required": ["results"],
                    "additionalProperties": False
                }
            }
        }
    )

    parsed = json.loads(response.output_text)
    return parsed["results"]


def insert_generated_questions(generated_questions):
    inserted_rows = []

    with connection.cursor() as cursor:
        for item in generated_questions:
            cursor.execute(
                """
                INSERT INTO spanish_vocab_test_bank (
                    lemma_rank,
                    question,
                    correct_answer,
                    distractor_1,
                    distractor_2,
                    distractor_3
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, question, correct_answer, distractor_1, distractor_2, distractor_3
                """,
                [
                    item["lemma_rank"],
                    item["question"],
                    item["correct_answer"],
                    item["distractor_1"],
                    item["distractor_2"],
                    item["distractor_3"],
                ]
            )

            inserted_rows.append(cursor.fetchone())

    return inserted_rows


def format_question_for_frontend(row):
    question_id, question, correct_answer, distractor_1, distractor_2, distractor_3 = row

    options = [
        correct_answer,
        distractor_1,
        distractor_2,
        distractor_3,
    ]

    random.shuffle(options)

    return {
        "question_id": question_id,
        "question": question,
        "options": options,
    }


def get_or_create_questions_for_counts(level_counts, used_question_ids):
    """
    level_counts example:
    {
        1: 3,
        2: 3,
        ...
    }

    Returns frontend-ready questions.
    """

    selected_rows = []

    for level, needed_count in level_counts.items():
        existing_rows = fetch_existing_questions_for_level(
            level=level,
            count=needed_count,
            used_question_ids=used_question_ids
        )

        selected_rows.extend(existing_rows)

        remaining_count = needed_count - len(existing_rows)

        if remaining_count <= 0:
            continue

        lemma_rows = fetch_lemmas_for_question_generation(
            level=level,
            count=remaining_count
        )

        generated_questions = generate_questions_with_openai(lemma_rows)
        inserted_rows = insert_generated_questions(generated_questions)

        selected_rows.extend(inserted_rows)

    random.shuffle(selected_rows)

    return [
        format_question_for_frontend(row)
        for row in selected_rows
    ]

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
    
from django.shortcuts import render, redirect
from django.db import connection


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
            payload = json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError:
            return JsonResponse(
                {"error": "Invalid JSON request."},
                status=400
            )

        action = payload.get("action")

        previous_answers = payload.get("previous_answers", [])
        all_answers = payload.get("all_answers", [])

        # The frontend sends previous_answers when asking for questions,
        # and all_answers when submitting a batch.
        answer_history = all_answers or previous_answers or []

        used_question_ids = []

        for answer in answer_history:
            question_id = answer.get("question_id")

            if question_id is not None:
                used_question_ids.append(int(question_id))

        try:
            if action == "get_questions":
                batch = int(payload.get("batch", 1))

                level_counts = choose_level_counts_for_next_batch(
                    all_answers=answer_history,
                    next_batch=batch
                )

                questions = get_or_create_questions_for_counts(
                    level_counts=level_counts,
                    used_question_ids=used_question_ids
                )

                if len(questions) != QUESTIONS_PER_BATCH:
                    return JsonResponse(
                        {
                            "error": f"Expected {QUESTIONS_PER_BATCH} questions, but generated {len(questions)}."
                        },
                        status=500
                    )

                return JsonResponse({
                    "status": "questions",
                    "questions": questions
                })

            if action in ["submit_batch", "submit_round"]:
                batch = int(payload.get("batch", payload.get("round", 1)))

                # This action receives the current batch's answers and all_answers.
                # The frontend already combines previous answers + current batch into all_answers.
                if not answer_history:
                    return JsonResponse(
                        {"error": "No answers were submitted."},
                        status=400
                    )

                next_batch = batch + 1

                if next_batch > TOTAL_BATCHES:
                    score = calculate_frontier_score(answer_history)

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
                        "score": score
                    })

                level_counts = choose_level_counts_for_next_batch(
                    all_answers=answer_history,
                    next_batch=next_batch
                )

                questions = get_or_create_questions_for_counts(
                    level_counts=level_counts,
                    used_question_ids=used_question_ids
                )

                if len(questions) != QUESTIONS_PER_BATCH:
                    return JsonResponse(
                        {
                            "error": f"Expected {QUESTIONS_PER_BATCH} questions, but generated {len(questions)}."
                        },
                        status=500
                    )

                return JsonResponse({
                    "status": "questions",
                    "questions": questions
                })

            if action == "complete_diagnostic":
                if not answer_history:
                    return JsonResponse(
                        {"error": "No answers were submitted."},
                        status=400
                    )

                score = calculate_frontier_score(answer_history)

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
                    "score": score
                })

            return JsonResponse(
                {"error": "Unsupported diagnostic action."},
                status=400
            )

        except Exception as e:
            print(f"Error handling vocab diagnostic POST: {e}")

            return JsonResponse(
                {"error": "Unable to process the diagnostic request."},
                status=500
            )

    # Users with no vocab score can always take the free diagnostic,
    # regardless of subscription status.
    if vocab_score == -1:
        return render(request, "vocab_test_diagnostic.html")

    if is_user_subscribed(request.user):
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