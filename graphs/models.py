from django.db import models
from users.models import UserProfile
from tweets.models import TweetNode


class UserGraph(models.Model):
    user = models.OneToOneField(
        UserProfile,
        on_delete=models.CASCADE,
        related_name="graph",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}'s graph"


class UserGraphNode(models.Model):
    SOURCE_CREATED = "created"
    SOURCE_PINNED = "pinned"
    SOURCE_SEEDED = "seeded"
    SOURCE_CHOICES = [
        (SOURCE_CREATED, "Created"),
        (SOURCE_PINNED, "Pinned"),
        (SOURCE_SEEDED, "Seeded"),
    ]

    graph = models.ForeignKey(
        UserGraph,
        on_delete=models.CASCADE,
        related_name="nodes",
    )
    tweet = models.ForeignKey(
        TweetNode,
        on_delete=models.CASCADE,
        related_name="graph_nodes",
    )
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("graph", "tweet")

    def __str__(self):
        return f"{self.graph.user.username} — {self.tweet.title} ({self.source})"


class UserGraphEdge(models.Model):
    graph = models.ForeignKey(
        UserGraph,
        on_delete=models.CASCADE,
        related_name="edges",
    )
    source_node = models.ForeignKey(
        UserGraphNode,
        on_delete=models.CASCADE,
        related_name="outgoing_edges",
    )
    target_node = models.ForeignKey(
        UserGraphNode,
        on_delete=models.CASCADE,
        related_name="incoming_edges",
    )
    weight = models.FloatField()

    class Meta:
        unique_together = ("graph", "source_node", "target_node")

    def __str__(self):
        return f"{self.source_node.tweet.title} → {self.target_node.tweet.title} ({self.weight:.2f})"


class GraphSession(models.Model):
    user = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name="graph_sessions",
    )
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} session @ {self.started_at}"


class NodeVisit(models.Model):
    session = models.ForeignKey(
        GraphSession,
        on_delete=models.CASCADE,
        related_name="node_visits",
    )
    tweet = models.ForeignKey(
        TweetNode,
        on_delete=models.CASCADE,
        related_name="visits",
    )
    visited_at = models.DateTimeField(auto_now_add=True)
    dwell_seconds = models.PositiveIntegerField(default=0)
    position_in_path = models.PositiveIntegerField()

    class Meta:
        ordering = ["position_in_path"]

    def __str__(self):
        return f"{self.session.user.username} visited {self.tweet.title} ({self.dwell_seconds}s)"


class EdgeTraversal(models.Model):
    session = models.ForeignKey(
        GraphSession,
        on_delete=models.CASCADE,
        related_name="edge_traversals",
    )
    from_tweet = models.ForeignKey(
        TweetNode,
        on_delete=models.CASCADE,
        related_name="traversals_from",
    )
    to_tweet = models.ForeignKey(
        TweetNode,
        on_delete=models.CASCADE,
        related_name="traversals_to",
    )
    traversed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.session.user.username}: {self.from_tweet.title} → {self.to_tweet.title}"
