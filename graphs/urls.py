from django.urls import path
from . import views

graph_urlpatterns = [
    path("feed/", views.feed_graph, name="graph-feed"),
    path("global/", views.global_graph, name="graph-global"),
    path("profile/<int:user_id>/", views.profile_graph, name="graph-profile"),
    path("node/<str:tweet_id>/", views.node_neighborhood, name="graph-node-neighborhood"),
    path("pin/", views.pin_node, name="graph-pin"),
]

interaction_urlpatterns = [
    path("session/", views.session_start, name="interaction-session-start"),
    path("session/end/", views.session_end, name="interaction-session-end"),
    path("visit/", views.record_visit, name="interaction-visit"),
    path("traverse/", views.record_traversal, name="interaction-traverse"),
]
