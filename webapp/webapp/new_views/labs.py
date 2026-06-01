from django.shortcuts import render, redirect
from django.db import connection
from django.http import JsonResponse
from ..decorators import registered_logged_in_required, subscribed_required
import vitalib
import json

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
                response = {}
                prompt_info = vitalib.Database.Writing.Submission(conn=connection, user_id=request.user.id).get_prompt(attempt_id=data.get("attempt_id"))
                prompt_text = prompt_info["text"]
                user_text = data.get("text")
                response["score"] = vitalib.Writing.Get(user_id=request.user.id, language=prompt_info["language"]).score(prompt_text=prompt_text, user_text=user_text)
                response["improvements"] = [
                    {
                    "title": "Use more precise descriptions",
                    "explanation": "Your writing is clear, but some descriptions are general. More specific language would make the paragraph stronger.",
                    "before": "The food was very good.",
                    "after": "The food was flavorful and freshly prepared."
                    }
                ]
                
                response["vocabulary"] = [
                    {
                    "word": "flavorful",
                    "lemma_id": 987,
                    "language": "en",
                    "definition": "Having a rich or pleasant taste.",
                    "explanation": "This word makes your description of the food more specific and natural.",
                    "before": "The food was very good.",
                    "after": "The food was flavorful and freshly prepared."
                    }
                ]
                response["status"] = "success"
            return JsonResponse(response)