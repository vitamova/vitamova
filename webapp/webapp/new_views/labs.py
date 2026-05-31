from django.shortcuts import render, redirect
from django.db import connection
from django.http import JsonResponse
from ..decorators import registered_logged_in_required, subscribed_required
import vitalib

@registered_logged_in_required
@subscribed_required
def writing(request):
    if request.method == "GET":
        return render(request, "modules/labs/writing.html", {
        })

    elif request.method == "POST":
        return JsonResponse({
            "status": "error",
            "error": "Method not yet implemented."
        }, status=405)