import jwt
import requests
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from .models import UserProfile


class CognitoAuthentication(BaseAuthentication):
    """
    Validates AWS Cognito JWT tokens on incoming requests.
    Extracts the user from the token and attaches their UserProfile.
    """

    def authenticate(self, request):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None

        token = auth_header.split(" ")[1]

        try:
            claims = self._decode_token(token)
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

    def _decode_token(self, token):
        jwks_url = (
            f"https://cognito-idp.{settings.COGNITO_REGION}.amazonaws.com/"
            f"{settings.COGNITO_USER_POOL_ID}/.well-known/jwks.json"
        )
        jwks = requests.get(jwks_url).json()
        public_keys = {key["kid"]: key for key in jwks["keys"]}

        headers = jwt.get_unverified_header(token)
        kid = headers.get("kid")
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
