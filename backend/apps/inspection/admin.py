"""Admin site for the inspection ontology.

Operational records (inspections, defects, reviews, actions, events) are read-only here:
their state changes go through apps.inspection.services so each change leaves an Event.
Model versions are the exception, because registering and activating them is the admin's job.
"""
from django.contrib import admin, messages

from .models import Action, Defect, Event, Inspection, Lot, ModelVersion, ProductionLine, ReviewTask
from .services import catalog


class ReadOnlyAdmin(admin.ModelAdmin):
    """View-only: Django renders the detail page read-only when change is denied but view is allowed."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ProductionLine)
class ProductionLineAdmin(admin.ModelAdmin):
    list_display = ("name", "site")


@admin.register(Lot)
class LotAdmin(admin.ModelAdmin):
    list_display = ("code", "line", "product_type", "status", "created_at")
    list_filter = ("status", "line")
    search_fields = ("code",)
    readonly_fields = ("status", "created_at")  # changed only by hold/release actions

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ModelVersion)
class ModelVersionAdmin(admin.ModelAdmin):
    list_display = ("name", "engine", "auto_ng_conf", "review_conf", "audit_rate", "is_active", "created_at")
    list_filter = ("engine", "is_active")
    actions = ["activate"]

    def get_readonly_fields(self, request, obj=None):
        fields = ["is_active", "created_at"]  # activation goes through the action below
        if obj is not None and obj.thresholds_locked():
            fields += list(ModelVersion.THRESHOLD_FIELDS) + ["name", "engine"]
        return fields

    def has_delete_permission(self, request, obj=None):
        return obj is None or not obj.thresholds_locked()

    @admin.action(description="선택한 버전을 운영 모델로 지정")
    def activate(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, "버전을 하나만 선택하세요.", level=messages.ERROR)
            return
        version = catalog.activate_model_version(queryset.get().pk, actor=request.user.get_username())
        self.message_user(request, f"{version.name} 버전이 운영 모델로 지정되었습니다.")


class DefectInline(admin.TabularInline):
    model = Defect
    extra = 0
    can_delete = False
    fields = ("defect_type", "confidence", "bbox", "origin", "status", "retrain_candidate")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Inspection)
class InspectionAdmin(ReadOnlyAdmin):
    list_display = ("id", "lot", "status", "verdict", "is_audit_sample", "engine_latency_ms", "captured_at")
    list_filter = ("status", "verdict", "is_audit_sample", "source", "model_version")
    search_fields = ("lot__code",)
    inlines = [DefectInline]


@admin.register(Defect)
class DefectAdmin(ReadOnlyAdmin):
    list_display = ("id", "inspection", "defect_type", "confidence", "origin", "status", "retrain_candidate")
    list_filter = ("status", "origin", "retrain_candidate")


@admin.register(ReviewTask)
class ReviewTaskAdmin(ReadOnlyAdmin):
    list_display = ("id", "inspection", "reason", "status", "decision", "reviewer", "created_at", "decided_at")
    list_filter = ("status", "reason", "decision")


@admin.register(Action)
class ActionAdmin(ReadOnlyAdmin):
    list_display = ("id", "lot", "action_type", "status", "owner", "opened_at", "closed_at")
    list_filter = ("status", "action_type")
    search_fields = ("lot__code", "owner")


@admin.register(Event)
class EventAdmin(ReadOnlyAdmin):
    list_display = ("at", "lot", "object_type", "object_id", "event", "actor")
    list_filter = ("object_type", "event")
    search_fields = ("lot__code", "actor")
