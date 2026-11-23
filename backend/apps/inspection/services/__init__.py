"""Use cases of the inspection domain.

Every function here runs in one transaction, checks the transition table, and writes the
matching Event rows. API views and Celery tasks call these instead of touching models
directly, so the audit trail cannot be skipped.
"""
