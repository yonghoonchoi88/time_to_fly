"""Role-based DRF permissions.

Roles are Django groups ordered from least to most privileged. A higher role
includes every lower one (qa_admin ⊃ shift_lead ⊃ inspector), and a superuser
always passes.
"""
from rest_framework.permissions import BasePermission

ROLE_ORDER = ["inspector", "shift_lead", "qa_admin"]

# Display names used on the admin site; group names stay in English.
ROLE_LABELS = {"inspector": "검수자", "shift_lead": "반장", "qa_admin": "관리자"}


def highest_role(user) -> str | None:
    """Returns the user's highest role name, or None if they hold none.

    A superuser is reported as the top role so clients treat them consistently
    with the permission checks below.
    """
    if not user or not user.is_authenticated:
        return None
    if user.is_superuser:
        return ROLE_ORDER[-1]
    names = set(user.groups.values_list("name", flat=True))
    for role in reversed(ROLE_ORDER):
        if role in names:
            return role
    return None


class HasRole(BasePermission):
    """Allows users whose highest role ranks at or above `required`."""

    required = ROLE_ORDER[0]

    def has_permission(self, request, view) -> bool:
        role = highest_role(request.user)
        return role is not None and ROLE_ORDER.index(role) >= ROLE_ORDER.index(self.required)


class IsInspector(HasRole):
    required = "inspector"


class IsShiftLead(HasRole):
    required = "shift_lead"


class IsQaAdmin(HasRole):
    required = "qa_admin"
