from django.urls import path
from . import views

urlpatterns = [
    path("home/", views.home_graph, name="graph-home"),
    path("global/", views.global_graph, name="graph-global"),
    path("node/<int:tweet_id>/", views.node_neighborhood, name="graph-node-neighborhood"),
]
