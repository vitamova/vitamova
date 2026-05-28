from django.shortcuts import render
from webapp.decorators import registered_logged_in_required, subscribed_required
from django.db import connection
from django.http import JsonResponse
import json
import vitalib


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
        if action != "search_lemmas" and action != "add_word":
            return JsonResponse(
                {
                    "status": "error",
                    "message": "Invalid action."
                },
                status=400
            )
        language = data.get("language")
        if action == "search_lemmas":
            query = data.get("query")
            lemmas = vitalib.Database.Vocab.Get(connection, request.user.id, language).lemma_starts_with(query)
            return JsonResponse(
                {
                    "status": "success",
                    "matches": lemmas
                }
            )
        elif action == "add_word":
            lemma_id = data.get("lemma_id")
            try:
                added = vitalib.Database.Vocab.Add(connection, request.user.id).lemma(lemma_id)
                if added["status"] == "added":
                    return JsonResponse(
                        {
                            "status": "success",
                            "message": "%s has been added to your vocabulary." % added["lemma"],
                            "lemma": added["lemma"]
                        }
                    )
                elif added["status"] == "already_exists":
                    return JsonResponse(
                        {
                            "status": "error",
                            "message": "%s is already in your vocabulary." % added["lemma"],
                            "lemma": added["lemma"]
                        }
                    )
            except:
                return JsonResponse(
                    {
                        "status": "error",
                        "message": "Something went wrong. Please try again."
                    },
                    status=400
                )
            
@registered_logged_in_required
@subscribed_required
def build(request):
    if request.method == "GET":
        language = request.GET.get("language", "es")
        return render(request, "modules/vocabulary/build.html", {
            "language": language
        })
    if request.method == "POST":
        # Get the data
        data = json.loads(request.body.decode("utf-8"))
        # Get language from data
        language = data.get("language", "es")
        action = data.get("action")
        if action not in [ "load_questions", "submit_answers", "add_to_bank", "flag_question"]:
            return JsonResponse({
                "status": "error",
                "message": "Invalid action."
            }, status=400)
        if action == "load_questions":
            # Check if the vocabulary score has improved
            vocab_score = vitalib.Database.UserInfo.Get(connection, request.user.id).score(language)
            new_score = vitalib.Test.Get(connection, request.user.id, language).new_score()
            if new_score["confidence"] == "solid" and new_score["score"] > vocab_score:
                # Just redirect home and it will update the score there
                return JsonResponse({
                    "status": "redirect_home"
                })
            else:
                questions = vitalib.Test.Get(connection, request.user.id, language).new_questions(count = 10)
                return JsonResponse({
                    "status": "ok",
                    "questions": questions
                })
        if action == "submit_answers":
            answers = data.get("answers", [])
            # Add 5 points per qestion answered
            points_added = vitalib.Database.Points(connection, request.user.id).add(len(answers) * 5, "vocab_builder")
            assert points_added["status"] == "ok", "Failed to add points for quiz."
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
def review(request):
    
    if request.method == "GET":
        language = request.GET.get("language", "es")
        return render(request, "modules/vocabulary/review.html", {
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
            review_items = vitalib.Database.Vocab.Get(connection, request.user.id, language).review_items()
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
            points_added = vitalib.Database.Points(connection, request.user.id).add(updated["points_added"], "vocab_review")
            assert points_added["status"] == "ok", "Failed to add points for review."
            return JsonResponse({
                "status": "ok"
            })