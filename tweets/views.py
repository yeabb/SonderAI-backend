from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction

from .models import TweetNode, EmbeddingReference
from .services.embedding import generate_embedding
from .services.pinecone import upsert_vector
from graphs.services.graph import build_profile_graph


class TweetListCreateView(APIView):
    def post(self, request):
        title = request.data.get("title", "").strip()
        content = request.data.get("content", "").strip()

        if not title:
            return Response({"detail": "title is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not content:
            return Response({"detail": "content is required."}, status=status.HTTP_400_BAD_REQUEST)
        if len(title) > 25:
            return Response({"detail": "title must be 25 characters or fewer."}, status=status.HTTP_400_BAD_REQUEST)
        if len(content) > 280:
            return Response({"detail": "content must be 280 characters or fewer."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            tweet = TweetNode.objects.create(
                user=request.user,
                title=title,
                content=content,
            )

            vector = generate_embedding(title, content)

            upsert_vector(
                tweet_id=str(tweet.id),
                vector=vector,
                metadata={
                    "text": f"{title} {content}",
                    "user_id": str(tweet.user.id),
                    "created_at": tweet.created_at.isoformat(),
                },
            )

            EmbeddingReference.objects.create(
                tweet=tweet,
                pinecone_vector_id=str(tweet.id),
            )

        # Rebuild the user's profile graph now that a new tweet exists
        build_profile_graph(request.user)

        return Response(
            {
                "id": str(tweet.id),
                "title": tweet.title,
                "content": tweet.content,
                "user": tweet.user.username,
                "created_at": tweet.created_at.isoformat(),
            },
            status=status.HTTP_201_CREATED,
        )


class TweetDetailView(APIView):
    def get(self, request, pk):
        return Response({"detail": "Not implemented yet."})

    def delete(self, request, pk):
        return Response(status=status.HTTP_204_NO_CONTENT)
