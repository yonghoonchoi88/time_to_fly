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


@pytest.mark.django_db
def test_token_login_then_me(api_client, make_user):
    make_user(username="choi", roles=("qa_admin",))
    res = api_client.post("/api/auth/token/", {"username": "choi", "password": "pw-for-tests"}, format="json")
    assert res.status_code == 200
    tokens = res.json()

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    me = api_client.get("/api/auth/me/")
    assert me.status_code == 200
    assert me.json()["role"] == "qa_admin"


@pytest.mark.django_db
def test_token_refresh_issues_new_access(api_client, make_user):
    make_user(username="choi")
    refresh = api_client.post(
        "/api/auth/token/", {"username": "choi", "password": "pw-for-tests"}, format="json"
    ).json()["refresh"]
    res = api_client.post("/api/auth/token/refresh/", {"refresh": refresh}, format="json")
    assert res.status_code == 200
    assert "access" in res.json()


@pytest.mark.django_db
def test_token_rejects_wrong_password(api_client, make_user):
    make_user(username="choi")
    res = api_client.post("/api/auth/token/", {"username": "choi", "password": "wrong"}, format="json")
    assert res.status_code == 401
