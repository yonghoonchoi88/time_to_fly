from django.apps import AppConfig


class AiGatewayConfig(AppConfig):
    """Client for the AI inference server. Holds no database tables (ADR 0001)."""

    name = "apps.ai_gateway"
    label = "ai_gateway"
