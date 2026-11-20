from rest_framework import serializers

from .permissions import highest_role


class MeSerializer(serializers.Serializer):
    """The signed-in user as clients need it: name, groups and effective role."""

    username = serializers.CharField()
    groups = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()

    def get_groups(self, user) -> list[str]:
        return sorted(user.groups.values_list("name", flat=True))

    def get_role(self, user) -> str | None:
        return highest_role(user)
