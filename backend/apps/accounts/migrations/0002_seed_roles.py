"""Creates the three role groups so every database gets them from `migrate`.

Role names are copied here on purpose: a migration must keep working even if
the application code that defines roles changes later.
"""
from django.db import migrations

ROLES = ["inspector", "shift_lead", "qa_admin"]


def create_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for name in ROLES:
        Group.objects.get_or_create(name=name)


def delete_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=ROLES).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_roles, delete_roles),
    ]
