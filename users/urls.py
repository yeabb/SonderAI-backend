from django.urls import path
from . import views

urlpatterns = [
    path("me/", views.me, name="user-me"),
    path("onboarding/", views.onboarding, name="user-onboarding"),
]
