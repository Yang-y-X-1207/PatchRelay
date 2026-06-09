from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8787
    token: str = "change-me"

    @field_validator("token")
    @classmethod
    def token_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("server.token must not be blank")
        return value


class RepoConfig(BaseModel):
    path: Path = Field(default_factory=lambda: Path.cwd())
    base_branch: str = "main"
    state_dir: Path = Field(default_factory=lambda: Path(".patchrelay"))


class WorkerConfig(BaseModel):
    default: Literal["auto", "codex", "claude"] = "auto"
    codex_command: str = "codex"
    claude_command: str = "claude"


class TestProfile(BaseModel):
    command: list[str]

    @field_validator("command")
    @classmethod
    def command_must_not_be_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("test profile command must not be empty")
        return value


class LimitsConfig(BaseModel):
    max_log_bytes: int = 1_048_576
    max_diff_bytes: int = 5_242_880
    task_timeout_seconds: int = 3_600


class Settings(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    repo: RepoConfig = Field(default_factory=RepoConfig)
    worker: WorkerConfig = Field(default_factory=WorkerConfig)
    tests: dict[str, TestProfile] = Field(
        default_factory=lambda: {"default": TestProfile(command=["python", "-m", "pytest"])}
    )
    limits: LimitsConfig = Field(default_factory=LimitsConfig)

    @field_validator("tests")
    @classmethod
    def tests_must_include_default(cls, value: dict[str, TestProfile]) -> dict[str, TestProfile]:
        if "default" not in value:
            raise ValueError("tests must include a default profile")
        return value


class ConfigError(RuntimeError):
    pass


def load_settings(config_path: str | Path | None = None) -> Settings:
    configured_path = config_path or os.getenv("PATCHRELAY_CONFIG") or "patchrelay.yaml"
    path = Path(configured_path)
    data: dict = {}

    if path.exists():
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc
        if loaded is not None:
            if not isinstance(loaded, dict):
                raise ConfigError(f"{path} must contain a YAML mapping")
            data = loaded

    token_override = os.getenv("PATCHRELAY_TOKEN")
    if token_override:
        data.setdefault("server", {})["token"] = token_override

    try:
        return Settings.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(str(exc)) from exc
