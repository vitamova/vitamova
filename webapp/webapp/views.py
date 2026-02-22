from django.shortcuts import render, redirect

def home(request):
    if not request.user.is_authenticated:
        return redirect('login')
    return render(request, 'home.html')

def login(request):
    return render(request, 'login.html')