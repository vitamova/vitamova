"""
URL configuration for vitamova project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.urls import path
from django.contrib import admin
from . import views
from . import authentication


urlpatterns = [
    path('admin/', admin.site.urls),
    path("login/",authentication.login,name='login'),
    path("logout/",authentication.logout,name='logout'),
    path("poetry/",views.poetry,name='poetry'),
    path("daily_article/",views.daily_article,name='daily_article'),
    path("submit_vocabulary/",views.submit_vocabulary,name='submit_vocabulary'),
    path("account/",views.account,name='account'),
    path("update_account/",authentication.update_account,name='update_account'),
    path("flashcards/",views.flashcards,name='flashcards'),
    path("signup/",authentication.signup,name='signup'),
    path("",views.home,name='home'),
]
