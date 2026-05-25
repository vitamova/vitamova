from django.shortcuts import render, redirect
from django.db import connection
from django.http import JsonResponse
from ..decorators import registered_logged_in_required
import vitalib

@registered_logged_in_required
def register_success(request):
    if vitalib.User.Registration(request.user.id, connection).recent():
        return render(request, "general/register_success.html")
    else:
        return redirect('/')

def prepare(request):
    db_settings = connection.settings_dict

    conn_params = {
        "host": db_settings.get("HOST"),
        "port": db_settings.get("PORT"),
        "dbname": db_settings.get("NAME"),
        "user": db_settings.get("USER"),
        "password": db_settings.get("PASSWORD"),
    }

    if request.method == "POST":
        try:
            result = vitalib.Database.Status(conn_params).start()

            if result.get("status") == "ok":
                return JsonResponse({
                    "status": "ok",
                    "message": "Database is ready."
                })

            else:
                return JsonResponse({
                    "status": "error",
                    "error": result.get("error", "Database is not ready.")
                }, status=503)

        except Exception as error:
            return JsonResponse({
                "status": "error",
                "error": str(error)
            }, status=503)

    elif request.method == "GET":
        redirect_uri = request.GET.get("redirect_uri", "/")

        if not redirect_uri.startswith("/"):
            redirect_uri = "/"

        return render(request, "general/prepare.html", {
            "redirect_uri": redirect_uri
        })

    return JsonResponse({
        "status": "error",
        "error": "Method not allowed."
    }, status=405)