import pytest


@pytest.mark.django_db
def test_me_requires_login(api_client):
    assert api_client.get("/api/auth/me/").status_code == 401


@pytest.mark.django_db
def test_me_reports_highest_role(api_client, make_user):
    api_client.force_authenticate(make_user(username="lee", roles=("inspector", "shift_lead")))
    res = api_client.get("/api/auth/me/")
    assert res.status_code == 200
    assert res.json() == {"username": "lee", "groups": ["inspector", "shift_lead"], "role": "shift_lead"}


@pytest.mark.django_db
def test_admin_login_page(client):
    assert client.get("/admin/login/").status_code == 200
