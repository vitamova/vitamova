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
    },
    {
        "code": "pt",
        "name": "Portuguese"
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
    level = vitalib.Database.UserInfo.Get(connection, request.user.id).level(language)
    language_name = vitalib.Transform.Language(language).code_to_name()
    new_level = vitalib.Test.Get(connection, request.user.id, language).new_level()
    edge_range = vitalib.Test.Get(connection, request.user.id, language).edge_range()
    level_mastery = vitalib.Test.Get(connection, request.user.id, language).level_mastery()
    # Get the level with the highest mastery
    best_level = max(level_mastery, key=lambda x: level_mastery[x]["mastery_confidence"])
    weekly_points = vitalib.Database.Points(connection, request.user.id).this_week()

    if new_level > level:
        vitalib.Database.UserInfo.Update(connection, request.user.id).level(language, new_level)
        return render(request, "general/new_level.html", {
            "first_name": request.user.first_name,
            "language": language,
            "language_name": language_name,
            "old_level": level,
            "new_level": new_level
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
            "review_count": review_count,
            "language": language,
            "language_name": language_name,
            "language_options": vitalib.Database.UserInfo.Get(connection, request.user.id).languages(),
            "dev": settings.SERVER_TYPE == 'dev',
            "mobile": mobile,
            "edge_range": edge_range,
            "level": level,
            "best_level": best_level,
            "best_level_mastery": level_mastery[best_level],
            "weekly_points": weekly_points
            })
    else:
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
@subscribed_required
def reading_practice(request):

    return render(request, "general/coming_soon.html", {
        "feature_name": "Reading Practice",
        "message": "Reading Practice is coming soon! In the meantime, you can review and practice the words you've already learned in the Review section.",
        "back_url": "/",
    })