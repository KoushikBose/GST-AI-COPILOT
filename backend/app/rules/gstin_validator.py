"""GSTIN structural validation.

This validates *format* (the 15-character structure, state code, PAN
embedding, checksum) deterministically — it does not verify a GSTIN is
actually registered/active with the GST department, which would require an
external GSTN API integration (out of scope here; see
app/integrations/ for where such an adapter would live).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# 2-digit state code + 10-char PAN + 1 entity code + 'Z' + 1 checksum digit/letter
_GSTIN_PATTERN = re.compile(
    r"^(?P<state_code>[0-3][0-9])"
    r"(?P<pan>[A-Z]{5}[0-9]{4}[A-Z])"
    r"(?P<entity_code>[0-9A-Z])"
    r"Z"
    r"(?P<checksum>[0-9A-Z])$"
)

_CHECKSUM_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# Valid Indian state/UT GST codes (01-38, excluding a few unassigned gaps).
_VALID_STATE_CODES = {f"{i:02d}" for i in range(1, 39)}


@dataclass
class GSTINValidationResult:
    is_valid: bool
    gstin: str
    state_code: str | None = None
    pan: str | None = None
    errors: list[str] = field(default_factory=list)


def _compute_checksum(gstin_without_checksum: str) -> str:
    """GSTIN check-digit algorithm (mod-36, weighted alternating 1/2)."""
    factor = 1
    total = 0
    for char in gstin_without_checksum:
        digit = _CHECKSUM_ALPHABET.index(char)
        addend = factor * digit
        addend = (addend // 36) + (addend % 36)
        total += addend
        factor = 2 if factor == 1 else 1
    remainder = total % 36
    check_code_point = (36 - remainder) % 36
    return _CHECKSUM_ALPHABET[check_code_point]


def validate_gstin(gstin: str | None) -> GSTINValidationResult:
    if not gstin:
        return GSTINValidationResult(is_valid=False, gstin="", errors=["GSTIN is missing."])

    cleaned = gstin.strip().upper()
    errors: list[str] = []

    if len(cleaned) != 15:
        errors.append(f"GSTIN must be exactly 15 characters (got {len(cleaned)}).")

    match = _GSTIN_PATTERN.match(cleaned)
    if match is None:
        errors.append("GSTIN does not match the required structural format.")
        return GSTINValidationResult(is_valid=False, gstin=cleaned, errors=errors)

    state_code = match.group("state_code")
    pan = match.group("pan")

    if state_code not in _VALID_STATE_CODES:
        errors.append(f"'{state_code}' is not a recognized GST state/UT code.")

    expected_checksum = _compute_checksum(cleaned[:-1])
    if expected_checksum != cleaned[-1]:
        errors.append("GSTIN checksum digit is invalid.")

    return GSTINValidationResult(
        is_valid=not errors,
        gstin=cleaned,
        state_code=state_code,
        pan=pan,
        errors=errors,
    )
