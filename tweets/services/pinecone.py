from pinecone import Pinecone
from django.conf import settings

_client = None
_index = None


def _get_index():
    global _client, _index
    if _index is None:
        _client = Pinecone(api_key=settings.PINECONE_API_KEY)
        _index = _client.Index(settings.PINECONE_INDEX_NAME)
    return _index


def upsert_vector(tweet_id: str, vector: list[float], metadata: dict) -> None:
    """
    Upsert a tweet embedding into Pinecone.
    tweet_id is used as the vector ID.
    """
    _get_index().upsert(vectors=[{
        "id": tweet_id,
        "values": vector,
        "metadata": metadata,
    }])


def query_similar(vector: list[float], top_k: int = 50) -> list[dict]:
    """
    Query Pinecone for the top_k most similar vectors.
    Returns a list of dicts with keys: id, score, values.
    """
    response = _get_index().query(
        vector=vector,
        top_k=top_k,
        include_values=True,
        include_metadata=True,
    )
    return [
        {
            "id": match.id,
            "score": match.score,
            "values": match.values,
            "metadata": match.metadata,
        }
        for match in response.matches
    ]
