from django.apps import AppConfig


class InspectionConfig(AppConfig):
    """The inspection ontology: Lot, Inspection, Defect, ReviewTask, Action, ModelVersion, Event.

    Engines and the AI server know nothing about these tables (ADR 0001); verdicts,
    reviews and field actions are decided and stored here.
    """

    name = "apps.inspection"
    label = "inspection"
    verbose_name = "검사 운영"
