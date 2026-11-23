"""Seeds the default line and an active mock model version.

With these rows a fresh `docker compose up` can record inspections against the mock
inference server (MODEL_VERSION=mock-0, ENGINE=mock) without any manual admin step.
The thresholds match the legacy FastAPI defaults. Values are copied here on purpose: a
migration must keep working even if application code changes later.
"""
from django.db import migrations

MOCK_VERSION = {
    "name": "mock-0",
    "engine": "mock",
    "auto_ng_conf": 0.7,
    "review_conf": 0.25,
    "audit_rate": 0.05,
    "note": "Seeded for development with the mock engine.",
}


def seed(apps, schema_editor):
    ProductionLine = apps.get_model("inspection", "ProductionLine")
    ModelVersion = apps.get_model("inspection", "ModelVersion")
    ProductionLine.objects.get_or_create(name="line-1")
    version, created = ModelVersion.objects.get_or_create(
        name=MOCK_VERSION["name"], defaults={k: v for k, v in MOCK_VERSION.items() if k != "name"}
    )
    if created and not ModelVersion.objects.filter(is_active=True).exists():
        version.is_active = True
        version.save(update_fields=["is_active"])


def unseed(apps, schema_editor):
    ModelVersion = apps.get_model("inspection", "ModelVersion")
    ModelVersion.objects.filter(name=MOCK_VERSION["name"], inspections__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("inspection", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]
