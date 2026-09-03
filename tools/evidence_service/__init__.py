"""Deterministic source-location service used by the future Skill."""

from .evidence import (
    EvidencePort,
    EvidenceRequestError,
    normalize_text,
    validate_card_configuration,
    validate_evidence_result,
)

__all__ = [
    "EvidencePort",
    "EvidenceRequestError",
    "normalize_text",
    "validate_card_configuration",
    "validate_evidence_result",
]
