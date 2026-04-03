from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(["GET"])
def me(request):
    # TODO: return serialized UserProfile for request.user
    return Response({"detail": "Not implemented yet."})


@api_view(["POST"])
def onboarding(request):
    # TODO: save interest tags for request.user, trigger initial graph seed
    return Response({"detail": "Not implemented yet."})
