from django.core.management import call_command
from django.test import Client


def test_collected_static_files_are_served_without_runserver(settings, tmp_path):
    """Mirrors the Docker image: collectstatic, then serve through the middleware stack only."""
    settings.STATIC_ROOT = tmp_path
    call_command("collectstatic", interactive=False, verbosity=0)

    client = Client()  # a fresh handler picks up the new STATIC_ROOT
    for path in ("/static/review/review.js", "/static/admin/css/base.css"):
        assert client.get(path).status_code == 200, path
