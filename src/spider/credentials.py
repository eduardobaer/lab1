"""Credential handling.

Credentials are loaded from any combination of:
- A JSON file (``--credentials-file path/to/creds.json``)
- Environment variables (``SPIDER_USERNAME``, ``SPIDER_EMAIL``,
  ``SPIDER_PASSWORD``, ``SPIDER_PHONE``)
- CLI flags (``--username``, ``--password``, ``--credential key=value``)

CLI flags override env vars override file values.

Credential VALUES are never sent to the LLM. Only field NAMES are exposed.
Claude requests ``fill_credential(field_name=..., element_id=...)`` and the
harness looks up the value and types it into the focused input field. This
keeps secrets out of the LLM's context window, the trace log, and the saved
config.
"""

import json
import os
from pathlib import Path
from typing import Optional


_ENV_FIELDS: dict[str, str] = {
    "SPIDER_USERNAME": "username",
    "SPIDER_EMAIL": "email",
    "SPIDER_PASSWORD": "password",
    "SPIDER_PHONE": "phone",
}


class Credentials:
    """A bag of named credential strings. Values are not exposed to the LLM."""

    def __init__(self, values: Optional[dict[str, str]] = None):
        self._values: dict[str, str] = {
            str(k): str(v) for k, v in (values or {}).items() if v is not None and v != ""
        }

    @classmethod
    def load(
        cls,
        *,
        file_path: Optional[Path] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        extra: Optional[dict[str, str]] = None,
    ) -> "Credentials":
        values: dict[str, str] = {}

        # Lowest precedence: file
        if file_path:
            data = json.loads(Path(file_path).read_text())
            if not isinstance(data, dict):
                raise ValueError(f"{file_path}: expected a JSON object of field → value")
            for k, v in data.items():
                if v is not None:
                    values[str(k)] = str(v)

        # Middle: env vars
        for env_name, field in _ENV_FIELDS.items():
            v = os.environ.get(env_name)
            if v:
                values[field] = v

        # Highest: explicit CLI args
        if username is not None:
            values["username"] = username
        if password is not None:
            values["password"] = password
        if extra:
            for k, v in extra.items():
                if v is not None:
                    values[str(k)] = str(v)

        return cls(values)

    def __bool__(self) -> bool:
        return bool(self._values)

    def field_names(self) -> list[str]:
        return sorted(self._values.keys())

    def get(self, name: str) -> Optional[str]:
        return self._values.get(name)

    def __contains__(self, name: object) -> bool:
        return name in self._values
