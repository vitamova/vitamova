from functools import wraps
from django.shortcuts import redirect
from django.db import connection
import vitalib

def registered_logged_in_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("/login/")

        if not vitalib.User.Registration(request.user.id, connection).is_valid():
            return redirect("/register/")

        #if not is_user_subscribed(request.user):
        #    return redirect("/subscribe/")

        return view_func(request, *args, **kwargs)

    return wrapper