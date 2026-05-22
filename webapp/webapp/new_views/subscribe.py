from webapp.decorators import registered_logged_in_required
from django.shortcuts import render

@registered_logged_in_required
def success(request):
    return render(request, "general/subscribe_success.html", {})