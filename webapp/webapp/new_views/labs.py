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
                sample_response = {
                    "status": "success",
                    "attempt_id": 123,
                    "server_now": "2026-05-31T15:00:00Z",
                    "started_at": "2026-05-31T15:00:00Z",
                    "expires_at": "2026-05-31T15:15:00Z",
                    "prompt": {
                        "id": 42,
                        "title": "Describe a recent meal",
                        "text": "Write about a meal you recently enjoyed. What did you eat, who were you with, and why did you enjoy it?"
                    }
                    }
            elif action == "autosave_writing":
                sample_response = {
                    "status": "success"
                    }
            elif action == "submit_writing":
                sample_response = {
                    "status": "success",
                    "attempt_id": 123,
                    "score": {
                        "value": 6,
                        "title": "Level 6 - Comfortable",
                        "description": "Your writing communicates your ideas effectively. Errors and awkward phrasing are noticeable, but they do not prevent understanding."
                    },
                    "improvements": [
                        {
                        "title": "Use more precise descriptions",
                        "explanation": "Your writing is clear, but some descriptions are general. More specific language would make the paragraph stronger.",
                        "before": "The food was very good.",
                        "after": "The food was flavorful and freshly prepared."
                        }
                    ],
                    "vocabulary": [
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
                }
            return JsonResponse(sample_response)