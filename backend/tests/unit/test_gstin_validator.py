"""Unit tests for GSTIN structural validation.

`27AAPFU0939F1ZV` is a widely published, publicly documented sample GSTIN
(used across GST explainer material) and is used here as a real-world
positive fixture for the checksum algorithm — not a fabricated test vector.
"""

from app.rules.gstin_validator import validate_gstin


class TestValidGSTIN:
    def test_known_valid_gstin_passes(self) -> None:
        result = validate_gstin("27AAPFU0939F1ZV")
        assert result.is_valid
        assert result.state_code == "27"
        assert result.pan == "AAPFU0939F"
        assert result.errors == []

    def test_lowercase_input_is_normalized(self) -> None:
        result = validate_gstin("27aapfu0939f1zv")
        assert result.is_valid

    def test_whitespace_is_stripped(self) -> None:
        result = validate_gstin("  27AAPFU0939F1ZV  ")
        assert result.is_valid


class TestInvalidGSTIN:
    def test_missing_gstin(self) -> None:
        result = validate_gstin(None)
        assert not result.is_valid
        assert "missing" in result.errors[0].lower()

    def test_empty_string(self) -> None:
        result = validate_gstin("")
        assert not result.is_valid

    def test_wrong_length(self) -> None:
        result = validate_gstin("27AAPFU0939F1Z")
        assert not result.is_valid
        assert any("15 characters" in e for e in result.errors)

    def test_invalid_state_code(self) -> None:
        # 99 is not an assigned GST state/UT code.
        result = validate_gstin("99AAPFU0939F1ZV")
        assert not result.is_valid

    def test_tampered_checksum_fails(self) -> None:
        # Same GSTIN as the valid fixture but with the last character changed.
        result = validate_gstin("27AAPFU0939F1ZA")
        assert not result.is_valid
        assert any("checksum" in e.lower() for e in result.errors)

    def test_malformed_pan_segment_fails(self) -> None:
        result = validate_gstin("27AAPFU0939F1Z!")
        assert not result.is_valid
