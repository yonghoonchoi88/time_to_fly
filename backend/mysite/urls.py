"""Top-level URL routes."""
from django.contrib import admin
from django.urls import include, path

from apps.core.views import review_queue

urlpatterns = [
    path("admin/", admin.site.urls),
    path("review/", review_queue, name="review-queue"),
    path("api/", include("apps.core.urls")),
    path("api/auth/", include("apps.accounts.urls")),
]
