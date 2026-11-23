"""Ontology object types. See docs/ontology.md for the design behind each object and link.

State fields (Lot.status, Defect.status, ...) are changed only through apps.inspection.services,
which check the transition table and write an Event in the same transaction. The admin site
shows these objects read-only for the same reason.

Foreign keys use PROTECT throughout: inspection history is an audit trail, so deleting a lot
or a model version must not silently take its inspections with it.
"""
from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from .enums import (
    ActionStatus,
    ActionType,
    DefectOrigin,
    DefectStatus,
    InspectionSource,
    InspectionStatus,
    LotStatus,
    ReviewDecision,
    ReviewReason,
    ReviewStatus,
    Verdict,
)

STATUS_LEN = 16


class ProductionLine(models.Model):
    name = models.CharField(max_length=64, unique=True)
    site = models.CharField(max_length=64, blank=True, default="")

    def __str__(self) -> str:
        return self.name


class Lot(models.Model):
    """A production batch. For the kimchi data set, one capture session is one lot."""

    line = models.ForeignKey(ProductionLine, on_delete=models.PROTECT, related_name="lots")
    code = models.CharField(max_length=64, unique=True)
    product_type = models.CharField(max_length=64, default="unknown")
    status = models.CharField(max_length=STATUS_LEN, choices=LotStatus.choices, default=LotStatus.OPEN)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self) -> str:
        return self.code


class ModelVersion(models.Model):
    """A served model plus the thresholds used to route its output.

    ``name`` must equal the ``version`` the inference server reports, so a worker can
    detect that the server is running a different model than the one being recorded.
    Thresholds live here, not in code, so verdicts stay comparable across versions; once
    an inspection has used them they are frozen (see ``save``).
    """

    THRESHOLD_FIELDS = ("auto_ng_conf", "review_conf", "audit_rate")

    name = models.CharField(max_length=64, unique=True)
    engine = models.CharField(max_length=32)
    weights_sha256 = models.CharField(max_length=64, blank=True, default="")
    auto_ng_conf = models.FloatField()
    review_conf = models.FloatField()
    audit_rate = models.FloatField(default=0.05)
    is_active = models.BooleanField(default=False)
    note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(review_conf__gte=0) & Q(review_conf__lte=F("auto_ng_conf")) & Q(auto_ng_conf__lte=1),
                name="model_version_threshold_order",
            ),
            models.CheckConstraint(
                condition=Q(audit_rate__gte=0) & Q(audit_rate__lte=1),
                name="model_version_audit_rate_range",
            ),
            # New inspections are recorded against exactly one version.
            models.UniqueConstraint(
                fields=["is_active"], condition=Q(is_active=True), name="single_active_model_version"
            ),
        ]

    def __str__(self) -> str:
        return self.name

    def thresholds_locked(self) -> bool:
        return self.pk is not None and self.inspections.exists()

    def save(self, *args, **kwargs):
        if self.pk is not None:
            stored = type(self).objects.filter(pk=self.pk).values(*self.THRESHOLD_FIELDS).first()
            changed = stored and any(stored[f] != getattr(self, f) for f in self.THRESHOLD_FIELDS)
            if changed and self.thresholds_locked():
                raise ValidationError(
                    f"thresholds of {self.name!r} are already used by inspections; register a new version instead"
                )
        super().save(*args, **kwargs)


class Inspection(models.Model):
    """One image inspected once.

    The row is created when the image is received (status ``queued``) and completed by
    the worker after inference, so verdict, size and engine latency are empty until then.
    """

    lot = models.ForeignKey(Lot, on_delete=models.PROTECT, related_name="inspections")
    model_version = models.ForeignKey(ModelVersion, on_delete=models.PROTECT, related_name="inspections")
    image_path = models.CharField(max_length=512, help_text="Relative to MEDIA_ROOT")
    source = models.CharField(max_length=STATUS_LEN, choices=InspectionSource.choices)
    status = models.CharField(
        max_length=STATUS_LEN, choices=InspectionStatus.choices, default=InspectionStatus.QUEUED
    )
    captured_at = models.DateTimeField()
    received_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    verdict = models.CharField(max_length=STATUS_LEN, choices=Verdict.choices, null=True, blank=True)
    image_width = models.PositiveIntegerField(null=True, blank=True)
    image_height = models.PositiveIntegerField(null=True, blank=True)
    # Engine time as measured by the inference server; end-to-end time is completed_at - received_at.
    engine_latency_ms = models.FloatField(null=True, blank=True)
    is_audit_sample = models.BooleanField(default=False)
    failure_reason = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["lot", "captured_at"]),
            models.Index(fields=["status", "received_at"]),
        ]

    def __str__(self) -> str:
        return f"Inspection #{self.pk} ({self.lot_id})"


class Defect(models.Model):
    inspection = models.ForeignKey(Inspection, on_delete=models.PROTECT, related_name="defects")
    defect_type = models.CharField(max_length=64)
    confidence = models.FloatField(null=True, blank=True)  # None for human-added defects
    bbox = models.JSONField(null=True, blank=True)  # [x, y, w, h] in source-image pixels
    origin = models.CharField(max_length=STATUS_LEN, choices=DefectOrigin.choices)
    status = models.CharField(max_length=STATUS_LEN, choices=DefectStatus.choices)
    retrain_candidate = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"Defect #{self.pk} {self.defect_type} ({self.status})"


class ReviewTask(models.Model):
    inspection = models.ForeignKey(Inspection, on_delete=models.PROTECT, related_name="review_tasks")
    reason = models.CharField(max_length=STATUS_LEN, choices=ReviewReason.choices)
    status = models.CharField(max_length=STATUS_LEN, choices=ReviewStatus.choices, default=ReviewStatus.PENDING)
    decision = models.CharField(max_length=STATUS_LEN, choices=ReviewDecision.choices, null=True, blank=True)
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="review_tasks"
    )
    created_at = models.DateTimeField(default=timezone.now)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            # A redelivered worker task must not queue the same image twice.
            models.UniqueConstraint(fields=["inspection"], name="one_review_task_per_inspection"),
        ]
        indexes = [models.Index(fields=["status", "created_at"])]

    def __str__(self) -> str:
        return f"ReviewTask #{self.pk} ({self.reason}, {self.status})"


class Action(models.Model):
    """A field action. Attached to a Lot because holds and rechecks happen per lot."""

    lot = models.ForeignKey(Lot, on_delete=models.PROTECT, related_name="actions")
    defect = models.ForeignKey(Defect, on_delete=models.PROTECT, null=True, blank=True, related_name="actions")
    action_type = models.CharField(max_length=STATUS_LEN, choices=ActionType.choices)
    status = models.CharField(max_length=STATUS_LEN, choices=ActionStatus.choices, default=ActionStatus.OPEN)
    owner = models.CharField(max_length=64, help_text="Person responsible on the floor; may not have an account")
    note = models.TextField(blank=True, default="")
    opened_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["status", "opened_at"])]

    def __str__(self) -> str:
        return f"Action #{self.pk} {self.action_type} ({self.status})"


class Event(models.Model):
    """Append-only audit log. Every state change writes one row; metrics are derived from it.

    ``lot`` is denormalised onto every event that belongs to a lot, so a lot's whole history
    is one indexed query instead of a join across five tables. Rows cannot be edited or
    deleted through the ORM instance API; bulk queryset updates are not blocked, so do not
    use them on this table.
    """

    lot = models.ForeignKey(Lot, on_delete=models.PROTECT, null=True, blank=True, related_name="events")
    object_type = models.CharField(max_length=32)
    object_id = models.BigIntegerField()
    event = models.CharField(max_length=64)
    actor = models.CharField(max_length=150)  # username, or "system" for the worker
    at = models.DateTimeField(default=timezone.now)
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["at", "id"]
        indexes = [
            models.Index(fields=["lot", "at"]),
            models.Index(fields=["object_type", "object_id"]),
        ]

    def __str__(self) -> str:
        return f"{self.at:%Y-%m-%d %H:%M:%S} {self.object_type}#{self.object_id} {self.event}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("events are append-only")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("events are append-only")
