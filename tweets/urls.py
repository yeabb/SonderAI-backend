from django.urls import path
from . import views

urlpatterns = [
    path("", views.TweetListCreateView.as_view(), name="tweet-list-create"),
    path("<int:pk>/", views.TweetDetailView.as_view(), name="tweet-detail"),
]
