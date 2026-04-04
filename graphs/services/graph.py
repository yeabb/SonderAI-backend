import math
import numpy as np
from datetime import timezone
from django.utils import timezone as django_timezone
from django.db import transaction

from tweets.models import TweetNode, EmbeddingReference
from tweets.services.embedding import generate_embedding
from tweets.services.pinecone import query_similar, upsert_vector
from graphs.models import (
    UserGraph,
    UserGraphNode,
    UserGraphEdge,
    GraphSession,
    NodeVisit,
    EdgeTraversal,
)

# How fast old interactions decay. At λ=0.01:
# - 30 days ago → 74% weight
# - 90 days ago → 40% weight
# - 180 days ago → 16% weight
DECAY_LAMBDA = 0.01

EDGE_THRESHOLD = 0.7
TOP_K = 50

# Signal weights — how much each interaction type contributes to the anchor
SIGNAL_WEIGHTS = {
    "pin": 5.0,
    "save": 3.0,
    "traversal_depth": 2.5,
    "dwell": 2.0,
    "visit": 1.5,
    "edge_traversal": 1.5,
    "like": 1.0,
}


def _decay_weight(base_weight: float, interaction_time) -> float:
    """
    Apply exponential recency decay to a signal weight.
    More recent interactions contribute more to the anchor.
    """
    now = django_timezone.now()
    days_ago = (now - interaction_time).total_seconds() / 86400
    return base_weight * math.exp(-DECAY_LAMBDA * days_ago)


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """
    Compute cosine similarity between two vectors.
    Returns a float in [-1, 1]. Higher = more similar.
    """
    a = np.array(vec_a)
    b = np.array(vec_b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def _compute_edges(candidates: list[dict], threshold: float = EDGE_THRESHOLD) -> list[dict]:
    """
    Given a list of candidates (each with 'id' and 'values'),
    compute pairwise cosine similarity and return edges where
    similarity >= threshold.
    """
    edges = []
    n = len(candidates)
    for i in range(n):
        for j in range(i + 1, n):
            similarity = _cosine_similarity(candidates[i]["values"], candidates[j]["values"])
            if similarity >= threshold:
                edges.append({
                    "source": candidates[i]["id"],
                    "target": candidates[j]["id"],
                    "weight": round(similarity, 4),
                })
    return edges


def _compute_anchor_embedding(user) -> list[float]:
    """
    Compute the anchor embedding for a user's feed graph.

    For new users (no interaction history): embed their interest tags.
    For returning users: compute a recency-decayed weighted centroid
    of all content they have meaningfully interacted with.

    Falls back to interest tags if no interaction data produces a valid centroid.
    """
    weighted_vectors = []
    total_weight = 0.0

    # --- Pinned nodes (highest weight) ---
    pinned_nodes = UserGraphNode.objects.filter(
        graph__user=user,
        source=UserGraphNode.SOURCE_PINNED,
    ).select_related("tweet__embedding_ref")

    for node in pinned_nodes:
        try:
            vector = _fetch_vector(str(node.tweet.id))
            if vector:
                w = _decay_weight(SIGNAL_WEIGHTS["pin"], node.added_at)
                weighted_vectors.append((w, vector))
                total_weight += w
        except Exception:
            continue

    # --- Saved tweets ---
    saved_tweets = user.saved_tweets.prefetch_related("embedding_ref").all()
    # Note: saved_by M2M is on TweetNode — querying from the user's perspective
    # This will be wired when the save interaction endpoint is built
    # For now this is a no-op placeholder

    # --- Node visits with dwell time (from graph sessions) ---
    visits = NodeVisit.objects.filter(
        session__user=user,
        dwell_seconds__gt=5,  # ignore bounces
    ).select_related("tweet").order_by("-visited_at")[:200]

    for visit in visits:
        try:
            vector = _fetch_vector(str(visit.tweet.id))
            if vector:
                # Scale dwell weight by how long they actually read it
                dwell_factor = min(visit.dwell_seconds / 60.0, 2.0)  # cap at 2x
                w = _decay_weight(SIGNAL_WEIGHTS["dwell"] * dwell_factor, visit.visited_at)
                weighted_vectors.append((w, vector))
                total_weight += w
        except Exception:
            continue

    # --- Edge traversals ---
    traversals = EdgeTraversal.objects.filter(
        session__user=user,
    ).select_related("to_tweet").order_by("-traversed_at")[:200]

    for traversal in traversals:
        try:
            vector = _fetch_vector(str(traversal.to_tweet.id))
            if vector:
                w = _decay_weight(SIGNAL_WEIGHTS["edge_traversal"], traversal.traversed_at)
                weighted_vectors.append((w, vector))
                total_weight += w
        except Exception:
            continue

    # --- Compute weighted centroid ---
    if weighted_vectors and total_weight > 0:
        dim = len(weighted_vectors[0][1])
        centroid = np.zeros(dim)
        for w, vec in weighted_vectors:
            centroid += w * np.array(vec)
        centroid /= total_weight
        return centroid.tolist()

    # --- Fallback: embed interest tags ---
    if user.interest_tags:
        tag_string = " ".join(user.interest_tags)
        return generate_embedding(tag_string, "")

    # --- Last resort: generic anchor ---
    return generate_embedding("technology science culture ideas society", "")


def _fetch_vector(tweet_id: str) -> list[float] | None:
    """
    Fetch a single tweet's embedding vector from Pinecone.
    Returns None if not found.
    """
    from tweets.services.pinecone import query_similar
    # We use a direct fetch via query with the tweet's own vector ID
    # Pinecone fetch by ID is more efficient — using the pinecone client directly
    from tweets.services.pinecone import _get_index
    result = _get_index().fetch(ids=[tweet_id])
    vectors = result.vectors
    if tweet_id in vectors:
        return vectors[tweet_id].values
    return None


def _serialize_graph(candidates: list[dict], edges: list[dict], tweet_map: dict) -> dict:
    """
    Serialize candidates and edges into the graph JSON format
    expected by the frontend.
    """
    nodes = []
    for candidate in candidates:
        tweet_id = candidate["id"]
        tweet = tweet_map.get(tweet_id)
        if not tweet:
            continue
        nodes.append({
            "id": tweet_id,
            "title": tweet.title,
            "content": tweet.content,
            "user": tweet.user.username,
            "created_at": tweet.created_at.isoformat(),
        })
    return {"nodes": nodes, "edges": edges}


def _recency_boost(candidates: list[dict]) -> list[dict]:
    """
    Re-rank Pinecone candidates by combining semantic similarity score
    with a recency decay factor based on the tweet's created_at metadata.

    final_score = similarity_score * e^(-λ * days_since_created)

    This ensures recent content gets a boost without completely burying
    highly relevant older content. Returns top TOP_K candidates sorted
    by final_score descending.
    """
    now = django_timezone.now()
    scored = []
    for c in candidates:
        created_at_str = c["metadata"].get("created_at") if c.get("metadata") else None
        if created_at_str:
            try:
                from datetime import datetime, timezone as dt_timezone
                created_at = datetime.fromisoformat(created_at_str).replace(tzinfo=dt_timezone.utc)
                days_ago = (now - created_at).total_seconds() / 86400
                recency_factor = math.exp(-DECAY_LAMBDA * days_ago)
            except Exception:
                recency_factor = 1.0
        else:
            recency_factor = 1.0

        final_score = c["score"] * recency_factor
        scored.append({**c, "final_score": final_score})

    scored.sort(key=lambda x: x["final_score"], reverse=True)
    return scored[:TOP_K]


def build_feed_graph(user) -> dict:
    """
    Build the user's personal feed graph.

    1. Compute recency-decayed anchor embedding from interaction history
    2. Query Pinecone for top-100 candidates, excluding already-visited tweets
       (exclusion happens inside the query — not post-filter — so the result
       set is always full-sized regardless of how much the user has seen)
    3. Re-rank by recency-boosted score, take top-50
    4. Build edges via pairwise cosine similarity
    5. Return graph JSON

    Called on session start — not on every page load.
    """
    anchor = _compute_anchor_embedding(user)

    # Collect visited tweet IDs to exclude from Pinecone query
    visited_ids = list(
        NodeVisit.objects.filter(session__user=user)
        .values_list("tweet_id", flat=True)
        .distinct()
    )
    visited_ids = [str(vid) for vid in visited_ids]

    pinecone_filter = {"id": {"$nin": visited_ids}} if visited_ids else None

    # Query larger pool (100) to give re-ranking room to work
    raw_candidates = query_similar(anchor, top_k=100, filter=pinecone_filter)

    if not raw_candidates:
        return {"nodes": [], "edges": []}

    # Re-rank by recency-boosted score, take top-50
    candidates = _recency_boost(raw_candidates)

    tweet_ids = [c["id"] for c in candidates]
    tweets = TweetNode.objects.filter(id__in=tweet_ids).select_related("user")
    tweet_map = {str(t.id): t for t in tweets}

    edges = _compute_edges(candidates)
    return _serialize_graph(candidates, edges, tweet_map)


def build_global_graph() -> dict:
    """
    Build the global/trending graph using a generic anchor.
    Used for logged-out users or as a fallback.
    """
    anchor = generate_embedding("technology science culture ideas society art philosophy", "")
    candidates = query_similar(anchor, top_k=TOP_K)

    if not candidates:
        return {"nodes": [], "edges": []}

    tweet_ids = [c["id"] for c in candidates]
    tweets = TweetNode.objects.filter(id__in=tweet_ids).select_related("user")
    tweet_map = {str(t.id): t for t in tweets}

    edges = _compute_edges(candidates)
    return _serialize_graph(candidates, edges, tweet_map)


def build_profile_graph(user) -> dict:
    """
    Build and persist a user's profile graph — all tweets they created,
    connected by semantic similarity.

    This is called when a tweet is created or deleted, not on every
    profile page load. The result is stored as UserGraph records.
    On profile page load, we just read the persisted records.
    """
    tweets = list(TweetNode.objects.filter(user=user).select_related("user"))

    if not tweets:
        return {"nodes": [], "edges": []}

    # Fetch all embedding vectors for this user's tweets from Pinecone
    tweet_ids = [str(t.id) for t in tweets]
    from tweets.services.pinecone import _get_index
    result = _get_index().fetch(ids=tweet_ids)

    candidates = []
    for tweet_id in tweet_ids:
        if tweet_id in result.vectors:
            candidates.append({
                "id": tweet_id,
                "values": result.vectors[tweet_id].values,
            })

    if not candidates:
        return {"nodes": [], "edges": []}

    edges = _compute_edges(candidates)
    tweet_map = {str(t.id): t for t in tweets}

    # Persist the graph
    with transaction.atomic():
        graph, _ = UserGraph.objects.get_or_create(user=user)

        # Clear existing nodes and edges — full rebuild on profile graph
        graph.nodes.all().delete()

        node_map = {}
        for tweet in tweets:
            node = UserGraphNode.objects.create(
                graph=graph,
                tweet=tweet,
                source=UserGraphNode.SOURCE_CREATED,
            )
            node_map[str(tweet.id)] = node

        for edge in edges:
            source_node = node_map.get(edge["source"])
            target_node = node_map.get(edge["target"])
            if source_node and target_node:
                UserGraphEdge.objects.create(
                    graph=graph,
                    source_node=source_node,
                    target_node=target_node,
                    weight=edge["weight"],
                )

    return _serialize_graph(candidates, edges, tweet_map)


def get_persisted_profile_graph(user) -> dict:
    """
    Read the precomputed profile graph from Postgres.
    Pure DB read — no computation. Called on every profile page load.
    """
    try:
        graph = UserGraph.objects.get(user=user)
    except UserGraph.DoesNotExist:
        return {"nodes": [], "edges": []}

    nodes_qs = graph.nodes.select_related("tweet__user").all()
    edges_qs = graph.edges.select_related("source_node__tweet", "target_node__tweet").all()

    nodes = [
        {
            "id": str(node.tweet.id),
            "title": node.tweet.title,
            "content": node.tweet.content,
            "user": node.tweet.user.username,
            "created_at": node.tweet.created_at.isoformat(),
            "source": node.source,
        }
        for node in nodes_qs
    ]

    edges = [
        {
            "source": str(edge.source_node.tweet.id),
            "target": str(edge.target_node.tweet.id),
            "weight": edge.weight,
        }
        for edge in edges_qs
    ]

    return {"nodes": nodes, "edges": edges}


def build_node_neighborhood(tweet_id: str) -> dict:
    """
    Build a local neighborhood graph centered on a specific tweet.
    Queries Pinecone using the tweet's own embedding as the anchor.
    """
    from tweets.services.pinecone import _get_index
    result = _get_index().fetch(ids=[tweet_id])

    if tweet_id not in result.vectors:
        return {"nodes": [], "edges": []}

    anchor = result.vectors[tweet_id].values
    candidates = query_similar(anchor, top_k=20)  # smaller neighborhood

    if not candidates:
        return {"nodes": [], "edges": []}

    tweet_ids = [c["id"] for c in candidates]
    tweets = TweetNode.objects.filter(id__in=tweet_ids).select_related("user")
    tweet_map = {str(t.id): t for t in tweets}

    edges = _compute_edges(candidates, threshold=0.65)  # slightly looser for neighborhoods
    return _serialize_graph(candidates, edges, tweet_map)
