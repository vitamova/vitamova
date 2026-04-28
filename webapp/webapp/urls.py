"""
URL configuration for webapp project.

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
from django.urls import path, include
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('login/', views.login, name='login'),
    path('accounts/', include('allauth.urls')),
    path('register/', views.register, name='register'),
    path('create-checkout-session/', views.create_checkout_session, name='create-checkout-session'),
    path('vocab-test/', views.vocab_test, name='vocab-test'),
    path('subscribe/', views.subscribe, name='subscribe'),
    path('flag-question/', views.flag_question, name='flag-question'),
]
