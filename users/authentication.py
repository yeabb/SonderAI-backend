import jwt
import requests
from django.conf import settings
from django.core.cache import cache
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from .models import UserProfile

JWKS_CACHE_KEY = "cognito_jwks"
JWKS_CACHE_TTL = 60 * 60  # 1 hour


class CognitoAuthentication(BaseAuthentication):
    """
    Validates AWS Cognito JWT tokens on incoming requests.
    Extracts the user from the token and attaches their UserProfile.

    JWKS (public keys) are cached in memory for 1 hour to avoid
    hitting the Cognito endpoint on every request.
    """

    def authenticate(self, request):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None

        token = auth_header.split(" ")[1]

        try:
            claims = self._decode_token(token)
        except AuthenticationFailed:
            raise
        except Exception as e:
            raise AuthenticationFailed(f"Invalid token: {str(e)}")

        cognito_id = claims.get("sub")
        if not cognito_id:
            raise AuthenticationFailed("Token missing subject claim.")

        try:
            user_profile = UserProfile.objects.get(cognito_id=cognito_id)
        except UserProfile.DoesNotExist:
            raise AuthenticationFailed("No user found for this token.")

        return (user_profile, token)

    def _get_jwks(self) -> dict:
        """
        Fetch Cognito's public JWKS, using Django's cache to avoid
        a network call on every request.
        """
        cached = cache.get(JWKS_CACHE_KEY)
        if cached:
            return cached

        jwks_url = (
            f"https://cognito-idp.{settings.COGNITO_REGION}.amazonaws.com/"
            f"{settings.COGNITO_USER_POOL_ID}/.well-known/jwks.json"
        )
        response = requests.get(jwks_url, timeout=5)
        response.raise_for_status()
        keys = {key["kid"]: key for key in response.json()["keys"]}
        cache.set(JWKS_CACHE_KEY, keys, JWKS_CACHE_TTL)
        return keys

    def _decode_token(self, token: str) -> dict:
        headers = jwt.get_unverified_header(token)
        kid = headers.get("kid")

        public_keys = self._get_jwks()

        if kid not in public_keys:
            # Key might have rotated — bust cache and retry once
            cache.delete(JWKS_CACHE_KEY)
            public_keys = self._get_jwks()
            if kid not in public_keys:
                raise AuthenticationFailed("Token key ID not recognized.")

        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(public_keys[kid])
        claims = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=settings.COGNITO_CLIENT_ID,
        )
        return claims
