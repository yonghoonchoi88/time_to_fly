from django.contrib.staticfiles import finders


def test_review_page_renders_with_static_assets(client):
    res = client.get("/review/")
    assert res.status_code == 200
    html = res.content.decode()
    assert "/static/review/review.js" in html
    assert "/static/review/review.css" in html


def test_review_static_files_are_discoverable():
    for path in ("review/review.js", "review/review.css", "review/mock/review_tasks.json", "review/mock/sample.png"):
        assert finders.find(path), path
