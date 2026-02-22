from django.shortcuts import render, redirect

#Need this to be UTF-8

def home(request):
    if not request.user.is_authenticated:
        return redirect('login')
    return render(request, 'home.html')

def login(request):
    return render(request, 'login.html')