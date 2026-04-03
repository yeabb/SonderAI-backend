import uuid
from django.db import models
from users.models import UserProfile


class TweetNode(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        UserProfile,
        on_delete=models.CASCADE,
        related_name="tweets",
    )
    title = models.CharField(max_length=25)
    content = models.TextField(max_length=280)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Threading
    parent_node = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="replies",
    )

    # Social interactions — data model ready, not exposed in MVP UI
    liked_by = models.ManyToManyField(
        UserProfile,
        related_name="liked_tweets",
        blank=True,
    )
    retweeted_by = models.ManyToManyField(
        UserProfile,
        related_name="retweeted_tweets",
        blank=True,
    )
    number_of_likes = models.PositiveIntegerField(default=0)
    number_of_retweets = models.PositiveIntegerField(default=0)
    is_retweet = models.BooleanField(default=False)
    original_tweet = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="retweets",
    )

    def __str__(self):
        return f"{self.user.username}: {self.title}"

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Tweet Node"
        verbose_name_plural = "Tweet Nodes"


class EmbeddingReference(models.Model):
    tweet = models.OneToOneField(
        TweetNode,
        on_delete=models.CASCADE,
        related_name="embedding_ref",
    )
    pinecone_vector_id = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Embedding for tweet {self.tweet_id}"

    class Meta:
        verbose_name = "Embedding Reference"
        verbose_name_plural = "Embedding References"
