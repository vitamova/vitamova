from functools import wraps
from django.shortcuts import redirect
from django.db import connection
from django.http import HttpResponseForbidden, JsonResponse
from django.conf import settings
import vitalib
import json

server_type = settings.SERVER_TYPE

def registered_logged_in_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("/login/")

        if not vitalib.User.Registration(request.user.id, connection).is_valid():
            return redirect("/register/")
        
        # Check the server_type whether this server is prod or dev
        # If it's dev only staff users can access the view
        # So if not staff, return 403 Forbidden
        if server_type == 'dev' and not request.user.is_staff:
            return HttpResponseForbidden("You are not allowed to access this page. Please go to app.vitamova.com to access the production version of the site.")
       
        return view_func(request, *args, **kwargs)

    return wrapper

def subscribed_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not vitalib.User.Subscription(request.user.id, request.user.email, connection).is_active():
            return redirect("/subscribe/")

        return view_func(request, *args, **kwargs)

    return wrapper

def noscore_or_subscribed_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):

        if vitalib.User.Subscription(request.user.id, request.user.email, connection).is_active():
            return view_func(request, *args, **kwargs)
        
        else:
            user_info = vitalib.Database.UserInfo.Get(
                connection,
                request.user.id
            ).data("vocab_score")

            vocab_score = user_info.get("vocab_score") if user_info else None

            if vocab_score == -1:
                return view_func(request, *args, **kwargs)
            else:
                if request.method == "GET":
                    return redirect("/subscribe/")
                elif request.method == "POST":
                    return JsonResponse(
                        {"status": "error", "message": "User must subscribe."},
                        status=400,
                    )

    return wrapper

def valid_language(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        connection = getattr(request, "conn", None)

        if connection is None:
            connection = vitalib.Database.Connection()

        # Let's make sure the user is submitting a valid language
        languages = vitalib.Database.UserInfo.Get(
            connection,
            request.user.id
        ).data(
            "target_language",
            "second_target_language"
        )

        language = None

        if request.method == "GET":
            language = request.GET.get("language", None)

        elif request.method == "POST":
            content_type = request.headers.get("Content-Type", "")

            if "application/json" in content_type:
                try:
                    data = json.loads(request.body) if request.body else {}
                except json.JSONDecodeError:
                    return HttpResponseForbidden("Invalid JSON.")

                language = data.get("language", None)

            else:
                language = request.POST.get("language", None)

        valid_languages = [
            value.strip()
            for value in languages.values()
            if value and value.strip()
        ]

        if language and language.strip() not in valid_languages:
            return HttpResponseForbidden("Invalid language.")

        return view_func(request, *args, **kwargs)

    return wrapper