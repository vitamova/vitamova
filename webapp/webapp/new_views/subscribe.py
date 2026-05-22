from webapp.decorators import registered_logged_in_required
from django.shortcuts import render, redirect
from django.db import connection
import vitalib

@registered_logged_in_required
def success(request):
    subscribed_recently = vitalib.User.Subscription(request.user.id, request.user.email, connection).recent()
    if subscribed_recently:
        user_target_language = vitalib.Database.UserInfo.Get(connection, request.user.id).data("target_language")["target_language"]
        language_name = vitalib.Transform.Language(user_target_language).code_to_name()
        return render(request, "general/subscribe_success.html", {
            "first_name": request.user.first_name,
            "language": language_name,
        })
    else:
        return redirect("/")