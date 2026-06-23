from __future__ import annotations

import re
from typing import Any

from patchrelay.config import LimitsConfig


SECRET_PATTERNS = [
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"(api[_-]?key\s*[=:]\s*)[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"(token\s*[=:]\s*)[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"(secret\s*[=:]\s*)[A-Za-z0-9._\-]+", re.IGNORECASE),
]


def redact_secrets(value: str) -> str:
    redacted = value
    for pattern in SECRET_PATTERNS:
        if pattern.pattern.lower().startswith("bearer"):
            redacted = pattern.sub("Bearer [REDACTED]", redacted)
        else:
            redacted = pattern.sub(r"\1[REDACTED]", redacted)
    return redacted


def truncate_text(value: str, max_bytes: int) -> tuple[str, bool]:
    raw = value.encode("utf-8")
    if len(raw) <= max_bytes:
        return value, False
    truncated_bytes = raw[:max_bytes]
    while truncated_bytes:
        try:
            truncated = truncated_bytes.decode("utf-8")
            return f"{truncated}\n[truncated]", True
        except UnicodeDecodeError:
            truncated_bytes = truncated_bytes[:-1]
    return "[truncated]", True


def clean_log(value: str, limits: LimitsConfig) -> tuple[str, bool]:
    return truncate_text(redact_secrets(value), limits.max_log_bytes)


def clean_diff(value: str, limits: LimitsConfig) -> tuple[str, bool]:
    return truncate_text(redact_secrets(value), limits.max_diff_bytes)


def build_summary_content(
    *,
    task_id: str,
    worker: str,
    status: str,
    changed_files: list[str],
    test_status: str,
    exit_code: int,
) -> dict[str, Any]:
    return {
        "taskId": task_id,
        "worker": worker,
        "status": status,
        "changedFiles": changed_files,
        "testStatus": test_status,
        "exitCode": exit_code,
    }
