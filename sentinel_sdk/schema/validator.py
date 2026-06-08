"""
Event schema validator.

Loads event.schema.json once at import time and exposes validate_event().
All four repos import this rather than duplicating validation logic.
"""

import json
from pathlib import Path

import jsonschema
from jsonschema import Draft202012Validator, ValidationError  # re-export ValidationError

_SCHEMA_DIR = Path(__file__).parent.parent.parent / "schemas"
_EVENT_SCHEMA: dict | None = None
_VALIDATOR: Draft202012Validator | None = None


def _get_validator() -> Draft202012Validator:
    global _EVENT_SCHEMA, _VALIDATOR
    if _VALIDATOR is None:
        schema_path = _SCHEMA_DIR / "event.schema.json"
        with open(schema_path) as f:
            _EVENT_SCHEMA = json.load(f)
        _VALIDATOR = Draft202012Validator(_EVENT_SCHEMA)
    return _VALIDATOR


def validate_event(event: dict) -> None:
    """Validate an event dict against event.schema.json.

    Raises jsonschema.ValidationError with a human-readable message on failure.
    Returns None on success.
    """
    validator = _get_validator()
    errors = list(validator.iter_errors(event))
    if errors:
        best = jsonschema.exceptions.best_match(errors)
        raise ValidationError(
            f"Event validation failed: {best.message}",
            validator=best.validator,
            path=best.absolute_path,
            cause=best.cause,
            context=best.context,
            schema=best.schema,
            schema_path=best.absolute_schema_path,
            instance=best.instance,
        )
