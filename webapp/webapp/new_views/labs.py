from django.shortcuts import render, redirect
from django.db import connection
from django.http import JsonResponse
from ..decorators import registered_logged_in_required, subscribed_required
import vitalib
import json
import datetime

@registered_logged_in_required
@subscribed_required
def writing(request):
    if request.method == "GET":
        return render(request, "modules/labs/writing.html", {
        })

    elif request.method == "POST":
        # Get JSON data from the request body
        data = json.loads(request.body)
        action = data.get("action")
        # Acceptable "action" values: start_writing, autosave_writing, submit_writing
        if action not in ["start_writing", "autosave_writing", "submit_writing"]:
            return JsonResponse({
                "status": "error",
                "error": "Invalid action."
            }, status=400)
        else:
            if action == "start_writing":
                response = {}
                response["prompt"] = vitalib.Database.Writing.Prompt(conn=connection, user_id=request.user.id, language=data.get("language")).get()
                response.update(vitalib.Database.Writing.Submission(conn=connection, user_id=request.user.id).create(prompt_id=response["prompt"]["id"]))
                response["status"] = "success"
            elif action == "autosave_writing":
                response = {
                    "status": "success"
                }
            elif action == "submit_writing":
                sample_request = {
                    "action": "submit_writing",
                    "attempt_id": 123,
                    "text": "Yesterday I had dinner...",
                    "character_count": 642,
                    "auto_submitted": False
                }
                # Make sure the text lenght is between 500 and 700 characters (inclusive)
                text_length = len(data.get("text", ""))
                if text_length < 500 or text_length > 700 or text_length != data.get("character_count"):
                    return JsonResponse({
                        "status": "error",
                        "error": "Text must be between 500 and 700 characters."
                    }, status=400)
                # Get the expiration time for the writing attempt and make sure it hasn't expired
                expiration_time = vitalib.Database.Writing.Submission(conn=connection, user_id=request.user.id).get_expiration(attempt_id=data.get("attempt_id"))
                # The expiration timestamp should be no more than 10 seconds in the past to account for any minor clock skew between the server and client
                now = datetime.datetime.now(datetime.timezone.utc)
                if expiration_time < now - datetime.timedelta(seconds=10):
                    return JsonResponse({
                        "status": "error",
                        "error": "Writing attempt has expired."
                    }, status=400)
                # Now add 100 XP to the user's points for completing the writing attempt
                points_added = vitalib.Database.Points(conn=connection, user_id=request.user.id).add(amount=100, task="Completed writing attempt")
                assert points_added["status"] == "ok", "Failed to add points for writing."

                # Now start building the response
                response = {}
                prompt_info = vitalib.Database.Writing.Submission(conn=connection, user_id=request.user.id).get_prompt(attempt_id=data.get("attempt_id"))
                prompt_text = prompt_info["text"]
                user_text = data.get("text")
                response["score"] = vitalib.Writing.Get(conn=connection, user_id=request.user.id, language=prompt_info["language"]).score(prompt_text=prompt_text, text=user_text)
                # Add score 
                score_added = vitalib.Database.Writing.Submission(conn=connection, user_id=request.user.id).add_score(attempt_id=data.get("attempt_id"), score=response["score"]["value"])
                assert score_added["status"] == "ok", "Failed to add score for writing."

                # Now get the rest of the feedback based on the user's writing
                response["improvements"] = vitalib.Writing.Get(conn=connection, user_id=request.user.id, language=prompt_info["language"]).improvements(prompt_text=prompt_text, text=user_text, score=response["score"]["value"])
                response["vocabulary"] = vitalib.Writing.Get(conn=connection, user_id=request.user.id, language=prompt_info["language"]).vocabulary(prompt_text=prompt_text, text=user_text)
                response["status"] = "success"
            return JsonResponse(response)