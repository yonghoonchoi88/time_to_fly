from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User
from .permissions import ROLE_LABELS


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "email", "role_labels", "is_staff", "is_active")
    list_filter = ("groups", "is_staff", "is_superuser", "is_active")

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("groups")

    @admin.display(description="역할")
    def role_labels(self, obj) -> str:
        return ", ".join(ROLE_LABELS.get(g.name, g.name) for g in obj.groups.all())
