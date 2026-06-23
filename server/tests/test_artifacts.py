from patchrelay.artifacts import clean_log, redact_secrets, truncate_text
from patchrelay.config import LimitsConfig


def test_redact_secrets() -> None:
    value = "Authorization: Bearer abc123 token=my-secret api_key=key123"

    redacted = redact_secrets(value)

    assert "abc123" not in redacted
    assert "my-secret" not in redacted
    assert "key123" not in redacted
    assert "[REDACTED]" in redacted


def test_truncate_text() -> None:
    value, truncated = truncate_text("abcdef", 3)

    assert truncated is True
    assert value.endswith("[truncated]")


def test_truncate_text_preserves_utf8_boundary() -> None:
    value, truncated = truncate_text("你好世界", 5)

    assert truncated is True
    assert value == "你\n[truncated]"


def test_clean_log_redacts_before_returning() -> None:
    value, truncated = clean_log("token=secret-value", LimitsConfig(max_log_bytes=1024))

    assert truncated is False
    assert "secret-value" not in value
