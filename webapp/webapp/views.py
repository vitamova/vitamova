from django.shortcuts import render, redirect
from django.db import connection

#Need this to be UTF-8

def home(request):
    if not request.user.is_authenticated:
        return redirect('login')

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1
            FROM registered_user
            WHERE user_id = %s
            LIMIT 1
            """,
            [request.user.id]
        )
        registered_user = cursor.fetchone()

    if not registered_user:
        return redirect('/register')

    return render(request, 'home.html')

def login(request):
    return render(request, 'login.html')

def register(request):
    if request.method == 'POST':
        # Handle registration logic here (e.g., create user, validate input)
        return redirect('home')  # Redirect to home after successful registration   
    elif request.method == 'GET':
        return render(request, 'register.html')