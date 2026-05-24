from django.shortcuts import render

def prepare(request):
    if request.method == "POST":
        # Handle any POST data if necessary
        pass
    elif request.method == "GET":
        return render(request, "general/prepare.html")