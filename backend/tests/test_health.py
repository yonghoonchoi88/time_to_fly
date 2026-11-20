import pytest
from django.db import OperationalError


@pytest.mark.django_db
def test_health_ok_without_login(api_client):
    res = api_client.get("/api/health/")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "db": "ok"}


@pytest.mark.django_db
def test_health_ignores_invalid_token(api_client):
    res = api_client.get("/api/health/", HTTP_AUTHORIZATION="Bearer not-a-token")
    assert res.status_code == 200


def test_health_reports_db_failure(api_client, monkeypatch):
    def broken_cursor(*args, **kwargs):
        raise OperationalError("database unavailable")

    monkeypatch.setattr("apps.core.views.connection.cursor", broken_cursor)
    res = api_client.get("/api/health/")
    assert res.status_code == 503
    assert res.json()["db"] == "error"
