from django.contrib import admin
from django.urls import path, include
from graphs.urls import graph_urlpatterns, interaction_urlpatterns

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/users/", include("users.urls")),
    path("api/v1/tweets/", include("tweets.urls")),
    path("api/v1/graph/", include(graph_urlpatterns)),
    path("api/v1/interactions/", include(interaction_urlpatterns)),
]
