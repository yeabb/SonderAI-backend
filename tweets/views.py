from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status


class TweetListCreateView(APIView):
    # TODO: implement list and create tweet logic
    def get(self, request):
        return Response({"detail": "Not implemented yet."})

    def post(self, request):
        return Response({"detail": "Not implemented yet."}, status=status.HTTP_201_CREATED)


class TweetDetailView(APIView):
    # TODO: implement retrieve and delete tweet logic
    def get(self, request, pk):
        return Response({"detail": "Not implemented yet."})

    def delete(self, request, pk):
        return Response(status=status.HTTP_204_NO_CONTENT)
