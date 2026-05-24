from django.shortcuts import render, redirect
from django.db import connection
from django.http import JsonResponse
import vitalib


def prepare(request):
    if request.method == "POST":
        try:
            result = vitalib.Database.Status(connection).start()

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

        if vitalib.Database.Status(connection).get():
            return redirect(redirect_uri)

        else:
            return render(request, "general/prepare.html", {
                "redirect_uri": redirect_uri
            })