from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status

from .models import UserProfile


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    """
    Returns the authenticated user's profile.
    """
    user = request.user
    return Response({
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "interest_tags": user.interest_tags,
        "created_at": user.created_at.isoformat(),
    })


@api_view(["POST"])
@permission_classes([AllowAny])
def onboarding(request):
    """
    Called by the frontend immediately after Cognito sign-up.
    Creates a UserProfile from the JWT claims if one doesn't exist yet.
    Idempotent — safe to call multiple times.

    Expected body:
        {
            "cognito_id": "<sub claim from JWT>",
            "username": "...",
            "email": "...",
            "interest_tags": ["tag1", "tag2"]   // optional
        }
    """
    cognito_id = request.data.get("cognito_id", "").strip()
    username = request.data.get("username", "").strip()
    email = request.data.get("email", "").strip()
    interest_tags = request.data.get("interest_tags", [])

    if not cognito_id:
        return Response({"detail": "cognito_id is required."}, status=status.HTTP_400_BAD_REQUEST)
    if not username:
        return Response({"detail": "username is required."}, status=status.HTTP_400_BAD_REQUEST)
    if not email:
        return Response({"detail": "email is required."}, status=status.HTTP_400_BAD_REQUEST)
    if not isinstance(interest_tags, list):
        return Response({"detail": "interest_tags must be a list."}, status=status.HTTP_400_BAD_REQUEST)

    profile, created = UserProfile.objects.get_or_create(
        cognito_id=cognito_id,
        defaults={
            "username": username,
            "email": email,
            "interest_tags": interest_tags,
        },
    )

    return Response(
        {
            "id": profile.id,
            "username": profile.username,
            "email": profile.email,
            "interest_tags": profile.interest_tags,
            "created": created,
        },
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )
