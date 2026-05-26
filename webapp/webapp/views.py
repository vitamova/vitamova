from django.shortcuts import render, redirect
from django.db import connection
from django.http import JsonResponse
from django.conf import settings
from .decorators import registered_logged_in_required, subscribed_required, noscore_or_subscribed_required, prepare_page
import json
import vitalib

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

# Views

@prepare_page
@registered_logged_in_required
def home(request):

    #See if language is specified as a query parameter
    language = request.GET.get("language")

    #Get target_language value from registered_user table to pass to template
    if not language:
        language = vitalib.Database.UserInfo.Get(connection, request.user.id).data("target_language")["target_language"] or "es"

    review_count = vitalib.Database.Vocab.Get(connection, request.user.id, language).review_count()
    vocab_score = vitalib.Database.UserInfo.Get(connection, request.user.id).score(language)
    language_name = vitalib.Transform.Language(language).code_to_name()
    new_score = vitalib.Test.Get(connection, request.user.id, language).new_score()

    if new_score["confidence"] == "solid" and new_score["score"] > vocab_score:
        vitalib.Database.UserInfo.Update(connection, request.user.id).score(language, new_score["score"])
        return render(request, "general/new_score.html", {
            "first_name": request.user.first_name,
            "language": language,
            "language_name": language_name,
            "old_score": vocab_score,
            "new_score": new_score["score"]
        })
    
    if vitalib.User.Subscription(request.user.id, request.user.email, connection).is_active():
        user_agent = request.META.get("HTTP_USER_AGENT", "").lower()
        mobile = any(device in user_agent for device in [
            "mobile",
            "android",
            "iphone",
            "ipad",
            "ipod",
            "windows phone",
        ])
        return render(request, "general/home.html", {
            "first_name": request.user.first_name,
            "user_email": request.user.email,
            "has_score": vocab_score != -1,
            "review_count": review_count,
            "language": language,
            "language_name": language_name,
            "language_options": vitalib.Database.UserInfo.Get(connection, request.user.id).languages(),
            "dev": settings.SERVER_TYPE == 'dev',
            "vocab_score": vocab_score,
            "mobile": mobile,
            "new_score_dict": new_score
            })
    else:
        # Not subscribed but can still take the test
        if vocab_score == -1:
            return render(request, "home_unsubscribed_noscore.html")
        else:
            # Otherwise, they gotta subscribe
            return redirect("/subscribe/")

@prepare_page
def login(request):
    if request.user.is_authenticated:
        return redirect('/')
    else:
        return render(request, 'general/login.html')

def register(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    
    if vitalib.User.Registration(request.user.id, connection).is_valid():
        return redirect('/account/')

    if request.method == 'POST':
        native_language = request.POST.get('native_language')
        target_language = request.POST.get('target_language')
        second_target_language = request.POST.get('second_target_language')
        agree_terms = request.POST.get('agree_terms')

        if not agree_terms:
            return render(request, 'general/register.html', {
                'first_name': request.user.first_name,
                'error': 'You must agree to the Terms and Conditions to continue.'
            })
        
        # vitalib.Database.Test(connection, request.user.username, "es").score_result(data.get("answers", []))
        vitalib.Database.UserInfo.Create(connection, request.user.id).data(
            native_language=native_language,
            target_language=target_language,
            second_target_language=second_target_language
        )

        return redirect('/general/register-success/')

    elif request.method == 'GET':
        return render(request, 'general/register.html', {
            'first_name': request.user.first_name,
            "native_language_options": SUPPORTED_NATIVE_LANGUAGES,
            "target_language_options": SUPPORTED_LANGUAGES
        })
    
@registered_logged_in_required
def account(request):
    if request.method == 'POST':
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
            "subscription_expiration"
        )
        return render(request, "general/account.html", {
            "first_name": request.user.first_name,
            "last_name": request.user.last_name,
            "user_email": request.user.email,
            "native_language": user_data.get("native_language"),
            "target_language": user_data.get("target_language"),
            "second_target_language": user_data.get("second_target_language"),
            "native_language_options": SUPPORTED_NATIVE_LANGUAGES,
            "target_language_options": SUPPORTED_LANGUAGES,
            "subscribed": vitalib.User.Subscription(request.user.id, request.user.email, connection).is_active(),
            "subscription_expiration": user_data.get("subscription_expiration"),
        })

@registered_logged_in_required
@noscore_or_subscribed_required
def vocab_test(request):
    if request.method == "GET":
        language = request.GET.get("language", "es")
        vocab_score = vitalib.Database.UserInfo.Get(connection, request.user.id).score(language)
        if vocab_score == -1:
            return render(request, "vocab_test_diagnostic.html", {
                "language": language
                }
            )
        
        else:
            if vitalib.User.Subscription(request.user.id, request.user.email, connection).is_active():
                return render(request, "modules/vocab_test_retest.html", {
                    "current_score": vocab_score,
                    "language": language
                })
            else:
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

        # Ensure the action is valid
        if action not in [
            "get_questions",
            "submit_batch",
            "complete_diagnostic",
            "get_retest_questions",
            "complete_retest",
            "resolve_retest_score",
            "flag_question"
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
                all_answers = data.get("all_answers", [])
                # Now get an actual score based on the answers
                score = vitalib.Test.Get(connection, request.user.id, language).score(all_answers)
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
                # Calculate frontier from vocab_score
                frontier = min((vocab_score // 1000) + 1, 6)
                questions = vitalib.Test.Get(connection, request.user.id, language).any_questions(type="retest", frontier=frontier)
                return JsonResponse({
                    "status": "questions",
                    "questions": questions
                })
            if action == "complete_retest":
                # Get parameter "answers" from data
                answers = data.get("answers", [])
                # Now get an actual score based on the answers
                score = vitalib.Test.Get(connection, request.user.id, language).score(answers)
                # "outcome" options are improved, downgrade_choice, or keep_current
                if score > vocab_score:
                    outcome = "improved"
                elif score//1000 < vocab_score//1000:
                    outcome = "downgrade_choice"
                else:
                    outcome = "keep_current"
                return JsonResponse({
                    "status": "complete",
                    "new_score": score,
                    "outcome": outcome
                })
            if action == "resolve_retest_score":
                # Get parameter "choice"
                choice = data.get("choice")
                # If "choice" is "accept_new" update the score
                if choice == "accept_new":
                    new_score = data.get("new_score")
                    # Make sure new_score is lower than the current score
                    # Don't want people to try to game the system
                    if new_score >= vocab_score:
                        return JsonResponse(
                            {"status": "error", "message": "Nice try. I'd recommend working on your vocabulary rather than trying to game the system."},
                            status=400
                        )
                    else:
                        vitalib.Database.UserInfo.Update(connection, request.user.id).score(language, new_score)
                        return JsonResponse({
                            "status": "ok"
                        })
                elif choice == "keep_current":
                    return JsonResponse({
                        "status": "ok"
                    })
                else:
                    return JsonResponse(
                        {"status": "error", "message": "Invalid JSON."},
                        status=400
                    )
        if action == "flag_question":
            question_id = data.get("question_id")
            language = data.get("language", "es")

            if not question_id:
                return JsonResponse(
                    {"status": "error", "message": "Missing question_id."},
                    status=400
                )

            flagged = vitalib.Database.Test.Questions(connection, request.user.id, language).flag(request.user.id, question_id)

            if flagged["status"] != "flagged":
                return JsonResponse(
                    {"status": "error", "message": "Unable to flag question."},
                    status=500
                )
            else:
                return JsonResponse({
                    "status": "flagged"
                })

@registered_logged_in_required
@subscribed_required
def vocab_builder(request):
    
    if request.method == "GET":
        language = request.GET.get("language", "es")
        return render(request, "modules/vocab_builder.html", {
            "language": language
        })
    if request.method == "POST":
        # Get the data
        data = json.loads(request.body.decode("utf-8"))
        # Get language from data
        language = data.get("language", "es")
        action = data.get("action")
        if action not in [ "load_questions", "submit_answers", "add_to_bank"]:
            return JsonResponse({
                "status": "error",
                "message": "Invalid action."
            }, status=400)
        if action == "load_questions":
            questions = vitalib.Test.Get(connection, request.user.id, language).new_questions(count = 10)
            return JsonResponse({
                "status": "ok",
                "questions": questions
            })
        if action == "submit_answers":
            answers = data.get("answers", [])
            # Get results based on answers
            missed = vitalib.Test.Get(connection, request.user.id, language).missed(answers)
            return JsonResponse({
                "status": "ok",
                "missed_questions": missed
            })
        if action == "add_to_bank":
            question_id = data.get("question_id")
            lemma_id = vitalib.Database.Test.Questions(connection, request.user.id, language).get_lemma_id(question_id)
            vitalib.Database.Vocab.Add(connection, request.user.id).lemma(lemma_id)
            return JsonResponse({
                "status": "ok",
                "added": True
            })

@registered_logged_in_required
@subscribed_required
def review(request):
    
    if request.method == "GET":
        language = request.GET.get("language", "es")
        return render(request, "modules/review.html", {
            "language": language
        })
    elif request.method == "POST":
        data = json.loads(request.body.decode("utf-8"))
        language = data.get("language", "es")
        action = data.get("action")

        if action not in ["load_review_items", "submit_review_result"]:
            return JsonResponse({
                "status": "error",
                "message": "Invalid action."
            }, status=400)

        if action == "load_review_items":
            review_items = vitalib.Database.Vocab.Get(connection, request.user.id, language).words()
            return JsonResponse({
                "status": "ok",
                "items": review_items
            })
        elif action == "submit_review_result":
            lemma_id = data.get("lemma_id")
            if data.get("remembered_correctly"):
                updated = vitalib.Database.Vocab.Update(connection, request.user.id).correct(lemma_id)
            else:
                updated = vitalib.Database.Vocab.Update(connection, request.user.id).incorrect(lemma_id)
            assert updated["status"] == "updated", "Failed to update review results."
            return JsonResponse({
                "status": "ok"
            })

@registered_logged_in_required
@subscribed_required
def reading_practice(request):

    return render(request, "general/coming_soon.html", {
        "feature_name": "Reading Practice",
        "message": "Reading Practice is coming soon! In the meantime, you can review and practice the words you've already learned in the Review section.",
        "back_url": "/",
    })