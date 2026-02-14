"""Shared contract definitions and validators."""

from .message_envelope import EnvelopeValidationError, validate_envelope

__all__ = ["EnvelopeValidationError", "validate_envelope"]
