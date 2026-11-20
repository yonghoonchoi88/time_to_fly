from django.db import DatabaseError, connection
from django.shortcuts import render
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@authentication_classes([])  # a stale token must not turn a health probe into a 401
@permission_classes([AllowAny])
def health(request):
    """GET /api/health/ — liveness plus a round trip to the database."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError:
        return Response({"status": "error", "db": "error"}, status=503)
    return Response({"status": "ok", "db": "ok"})


def review_queue(request):
    """GET /review/ — review queue screen. Runs on mock data until the domain API moves here (#6)."""
    return render(request, "review/index.html")
