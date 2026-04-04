from django.urls import path
from . import views

urlpatterns = [
    path("feed/", views.feed_graph, name="graph-feed"),
    path("global/", views.global_graph, name="graph-global"),
    path("profile/<int:user_id>/", views.profile_graph, name="graph-profile"),
    path("node/<str:tweet_id>/", views.node_neighborhood, name="graph-node-neighborhood"),
]
