"""Service errors. The API layer maps them to HTTP status codes."""


class NotFound(LookupError):
    """The referenced object does not exist (HTTP 404)."""


class Conflict(RuntimeError):
    """The request is valid but the current state does not allow it (HTTP 409)."""


class Invalid(ValueError):
    """The request refers to objects or values that do not fit together (HTTP 422)."""
