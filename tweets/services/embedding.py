from openai import OpenAI
from django.conf import settings

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = OpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


def generate_embedding(title: str, content: str) -> list[float]:
    """
    Generate a 1536-dim embedding for a tweet using OpenAI text-embedding-3-small.
    Combines title and content into a single input string.
    """
    text = f"{title} {content}".strip()
    response = _get_client().embeddings.create(
        model="text-embedding-3-small",
        input=text,
        dimensions=1536,
    )
    return response.data[0].embedding
