"""``python manage.py ai_check``: print the AI server's /health and /model.

Exits with status 1 if the server is unreachable or reports itself unhealthy, so it can
gate scripts and container start-up checks.
"""
import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.ai_gateway import services


class Command(BaseCommand):
    help = "Check the AI inference server: prints /health and /model, exits 1 on failure."

    def handle(self, *args, **options):
        base_url = settings.FASTAPI_BASE_URL
        try:
            health = services.health()
            model = services.model_info()
        except services.AiServerError as exc:
            raise CommandError(f"AI server check failed ({base_url}): {exc}") from exc

        self.stdout.write(f"ai-server: {base_url}")
        self.stdout.write("health: " + json.dumps(health, ensure_ascii=False))
        self.stdout.write("model:  " + json.dumps(model, ensure_ascii=False))

        if health.get("status") != "ok" or health.get("model_loaded") is False:
            raise CommandError("AI server is up but not ready (status != ok or model not loaded)")
        self.stdout.write(self.style.SUCCESS("ok"))
