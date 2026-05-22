from webapp.decorators import registered_logged_in_required, subscribed_required
from django.shortcuts import render, redirect
from django.db import connection
import vitalib

STRIPE_PUBLIC_KEY= "pk_live_51RIChJKOiNtX3WewnOeHxiL99XltNWm2TluZew2fn6fzcmuHJ3R2x7EuLbbNpb74k1gnHlSRPHOoFJsFTEd5z8fp00rYr00NmV"

@registered_logged_in_required
def subscribe(request):

    if vitalib.User.Subscription(request.user.id, request.user.email, connection).is_active():
        return redirect("home")
    
    # Get user's score and language
    user_data = vitalib.Database.UserInfo.Get(connection, request.user.id).data()

    return render(request, "general/subscribe.html", {
        "stripe_public_key": STRIPE_PUBLIC_KEY,
        "score": vitalib.Database.UserInfo.Get(connection, request.user.id).data("vocab_score")["vocab_score"],
        "language": vitalib.Transform.Language(user_data["target_language"]).code_to_name(),
        "first_name": request.user.first_name,
    })

@registered_logged_in_required
@subscribed_required
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