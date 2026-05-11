from functools import wraps
from django.shortcuts import redirect
from django.db import connection
from django.http import HttpResponseForbidden
from pathlib import Path
import vitalib

BASE_DIR = Path(__file__).resolve().parent.parent
# Save server_type as a global variable
server_type_path = Path.home() / 'data' / 'server_type.txt'
with open(server_type_path, 'r') as f:
    server_type = f.read().strip()

def registered_logged_in_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("/login/")

        if not vitalib.User.Registration(request.user.id, connection).is_valid():
            return redirect("/register/")
        
        # Check in ˜/data/server_type whether this server is prod or dev
        # If it's dev only staff users can access the view
        # So if not staff, return 403 Forbidden
        if server_type == 'dev' and not request.user.is_staff:
            return HttpResponseForbidden("You are not allowed to access this page. Please go to app.vitamova.com to access the production version of the site.")
       
        return view_func(request, *args, **kwargs)

    return wrapper