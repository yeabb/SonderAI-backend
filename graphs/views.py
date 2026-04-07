import threading
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from users.models import UserProfile
from tweets.models import TweetNode
from graphs.models import (
    GraphSession,
    NodeVisit,
    EdgeTraversal,
    UserGraph,
    UserGraphNode,
    UserGraphEdge,
)
from graphs.services.graph import (
    build_feed_graph,
    build_global_graph,
    build_profile_graph,
    get_persisted_profile_graph,
    build_node_neighborhood,
    _incremental_anchor_update,
    _fetch_vector,
    _cosine_similarity,
    SIGNAL_WEIGHTS,
)


# ── Graph endpoints ───────────────────────────────────────────────────────────

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


@api_view(["POST"])
def pin_node(request):
    """
    Pin a tweet to the user's graph.

    Adds a UserGraphNode (source=pinned), computes edges against all
    existing profile graph nodes, and triggers an immediate incremental
    anchor update — pin is the strongest signal.

    Expected body: { "tweet_id": "<uuid>" }
    """
    tweet_id = request.data.get("tweet_id", "").strip()
    if not tweet_id:
        return Response({"detail": "tweet_id is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        tweet = TweetNode.objects.get(id=tweet_id)
    except TweetNode.DoesNotExist:
        return Response({"detail": "Tweet not found."}, status=status.HTTP_404_NOT_FOUND)

    graph, _ = UserGraph.objects.get_or_create(user=request.user)

    # Idempotent — don't duplicate if already pinned
    node, created = UserGraphNode.objects.get_or_create(
        graph=graph,
        tweet=tweet,
        defaults={"source": UserGraphNode.SOURCE_PINNED},
    )

    if created:
        # Compute edges between the new pinned node and all existing nodes
        existing_nodes = UserGraphNode.objects.filter(graph=graph).exclude(id=node.id)
        pinned_vector = _fetch_vector(tweet_id)

        if pinned_vector:
            for existing_node in existing_nodes:
                existing_vector = _fetch_vector(str(existing_node.tweet.id))
                if not existing_vector:
                    continue
                similarity = _cosine_similarity(pinned_vector, existing_vector)
                if similarity >= 0.7:
                    UserGraphEdge.objects.get_or_create(
                        graph=graph,
                        source_node=node,
                        target_node=existing_node,
                        defaults={"weight": round(similarity, 4)},
                    )

            # Immediate incremental anchor update — pin is highest-weight signal
            def _update():
                graph.refresh_from_db()
                if graph.cached_anchor:
                    _incremental_anchor_update(graph, pinned_vector, SIGNAL_WEIGHTS["pin"])

            threading.Thread(target=_update, daemon=True).start()

    return Response({"pinned": created}, status=status.HTTP_200_OK)


# ── Interaction endpoints ─────────────────────────────────────────────────────

@api_view(["POST"])
def session_start(request):
    """
    Called when the user opens the app and a new graph session begins.
    Returns the session ID — the frontend includes this in subsequent
    visit and traversal events.

    Response: { "session_id": <int> }
    """
    session = GraphSession.objects.create(user=request.user)
    return Response({"session_id": session.id}, status=status.HTTP_201_CREATED)


@api_view(["POST"])
def session_end(request):
    """
    Called when the user closes the app or navigates away.
    Marks the session as ended and triggers an incremental anchor update
    if there was significant activity during the session.

    Significant activity = pin OR 3+ visits over 10s OR 2+ traversals.

    Expected body: { "session_id": <int> }
    """
    session_id = request.data.get("session_id")
    if not session_id:
        return Response({"detail": "session_id is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        session = GraphSession.objects.get(id=session_id, user=request.user)
    except GraphSession.DoesNotExist:
        return Response({"detail": "Session not found."}, status=status.HTTP_404_NOT_FOUND)

    session.ended_at = timezone.now()
    session.save(update_fields=["ended_at"])

    # Check for significant activity
    meaningful_visits = session.node_visits.filter(dwell_seconds__gte=10).count()
    traversal_count = session.edge_traversals.count()
    significant = meaningful_visits >= 3 or traversal_count >= 2

    if significant:
        user = request.user

        def _update():
            _fold_session_into_anchor(user, session)

        threading.Thread(target=_update, daemon=True).start()

    return Response({"detail": "Session ended."}, status=status.HTTP_200_OK)


def _fold_session_into_anchor(user, session):
    """
    Fold a session's interaction signals into the cached anchor
    via a single incremental update.
    """
    import numpy as np

    weighted_vectors = []
    total_weight = 0.0

    for visit in session.node_visits.filter(dwell_seconds__gte=10).select_related("tweet"):
        vector = _fetch_vector(str(visit.tweet.id))
        if vector:
            dwell_factor = min(visit.dwell_seconds / 60.0, 2.0)
            w = SIGNAL_WEIGHTS["dwell"] * dwell_factor
            weighted_vectors.append((w, vector))
            total_weight += w

    for traversal in session.edge_traversals.select_related("to_tweet"):
        vector = _fetch_vector(str(traversal.to_tweet.id))
        if vector:
            w = SIGNAL_WEIGHTS["edge_traversal"]
            weighted_vectors.append((w, vector))
            total_weight += w

    if not weighted_vectors or total_weight == 0:
        return

    dim = len(weighted_vectors[0][1])
    centroid = np.zeros(dim)
    for w, vec in weighted_vectors:
        centroid += w * np.array(vec)
    centroid /= total_weight

    try:
        graph = UserGraph.objects.get(user=user)
        if graph.cached_anchor:
            _incremental_anchor_update(graph, centroid.tolist(), total_weight)
    except UserGraph.DoesNotExist:
        pass


@api_view(["POST"])
def record_visit(request):
    """
    Record or update a node visit within a session.

    First call (no dwell_seconds): creates the NodeVisit.
    Second call (with dwell_seconds): updates dwell time on the existing visit.

    Expected body:
        {
            "session_id": <int>,
            "tweet_id": "<uuid>",
            "position_in_path": <int>,
            "dwell_seconds": <int>   // optional, sent on second call
        }
    """
    session_id = request.data.get("session_id")
    tweet_id = request.data.get("tweet_id", "").strip()
    position = request.data.get("position_in_path")
    dwell_seconds = request.data.get("dwell_seconds")

    if not session_id:
        return Response({"detail": "session_id is required."}, status=status.HTTP_400_BAD_REQUEST)
    if not tweet_id:
        return Response({"detail": "tweet_id is required."}, status=status.HTTP_400_BAD_REQUEST)
    if position is None:
        return Response({"detail": "position_in_path is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        session = GraphSession.objects.get(id=session_id, user=request.user)
    except GraphSession.DoesNotExist:
        return Response({"detail": "Session not found."}, status=status.HTTP_404_NOT_FOUND)

    try:
        tweet = TweetNode.objects.get(id=tweet_id)
    except TweetNode.DoesNotExist:
        return Response({"detail": "Tweet not found."}, status=status.HTTP_404_NOT_FOUND)

    visit, created = NodeVisit.objects.get_or_create(
        session=session,
        tweet=tweet,
        defaults={"position_in_path": position, "dwell_seconds": 0},
    )

    if not created and dwell_seconds is not None:
        visit.dwell_seconds = dwell_seconds
        visit.save(update_fields=["dwell_seconds"])

    return Response({"visit_id": visit.id, "created": created}, status=status.HTTP_200_OK)


@api_view(["POST"])
def record_traversal(request):
    """
    Record an edge traversal — user followed a graph edge from one node to another.

    Expected body:
        {
            "session_id": <int>,
            "from_tweet_id": "<uuid>",
            "to_tweet_id": "<uuid>"
        }
    """
    session_id = request.data.get("session_id")
    from_tweet_id = request.data.get("from_tweet_id", "").strip()
    to_tweet_id = request.data.get("to_tweet_id", "").strip()

    if not session_id:
        return Response({"detail": "session_id is required."}, status=status.HTTP_400_BAD_REQUEST)
    if not from_tweet_id:
        return Response({"detail": "from_tweet_id is required."}, status=status.HTTP_400_BAD_REQUEST)
    if not to_tweet_id:
        return Response({"detail": "to_tweet_id is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        session = GraphSession.objects.get(id=session_id, user=request.user)
    except GraphSession.DoesNotExist:
        return Response({"detail": "Session not found."}, status=status.HTTP_404_NOT_FOUND)

    try:
        from_tweet = TweetNode.objects.get(id=from_tweet_id)
        to_tweet = TweetNode.objects.get(id=to_tweet_id)
    except TweetNode.DoesNotExist:
        return Response({"detail": "One or both tweets not found."}, status=status.HTTP_404_NOT_FOUND)

    traversal = EdgeTraversal.objects.create(
        session=session,
        from_tweet=from_tweet,
        to_tweet=to_tweet,
    )

    return Response({"traversal_id": traversal.id}, status=status.HTTP_201_CREATED)
