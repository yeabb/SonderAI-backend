from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from users.models import UserProfile
from graphs.services.graph import (
    build_feed_graph,
    build_global_graph,
    build_profile_graph,
    get_persisted_profile_graph,
    build_node_neighborhood,
)


@api_view(["GET"])
def feed_graph(request):
    """
    Returns the user's personal feed graph.
    Rebuilt on session start using a recency-decayed anchor embedding.
    """
    graph = build_feed_graph(request.user)
    return Response(graph)


@api_view(["GET"])
def global_graph(request):
    """
    Returns the global/trending graph using a generic anchor.
    Useful for new users with no interaction history yet.
    """
    graph = build_global_graph()
    return Response(graph)


@api_view(["GET"])
def profile_graph(request, user_id):
    """
    Returns a user's profile graph — all tweets they created, connected
    by semantic similarity. Reads from precomputed Postgres records.
    Pure DB read, no computation on load.
    """
    try:
        profile_user = UserProfile.objects.get(id=user_id)
    except UserProfile.DoesNotExist:
        return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

    graph = get_persisted_profile_graph(profile_user)
    return Response(graph)


@api_view(["GET"])
def node_neighborhood(request, tweet_id):
    """
    Returns the local neighborhood graph for a specific node.
    Anchored on that tweet's embedding with a smaller top_k
    and slightly looser edge threshold.
    """
    graph = build_node_neighborhood(tweet_id)
    if not graph["nodes"]:
        return Response({"detail": "Node not found."}, status=status.HTTP_404_NOT_FOUND)
    return Response(graph)
