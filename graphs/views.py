from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(["GET"])
def home_graph(request):
    # TODO: build and return personal graph for request.user
    return Response({"detail": "Not implemented yet."})


@api_view(["GET"])
def global_graph(request):
    # TODO: build and return global/trending graph
    return Response({"detail": "Not implemented yet."})


@api_view(["GET"])
def node_neighborhood(request, tweet_id):
    # TODO: return local neighborhood graph for a given node
    return Response({"detail": "Not implemented yet."})
