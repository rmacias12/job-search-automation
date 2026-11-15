"""Resolve configured 1Password references without exporting secret values."""
import json
import os
from pathlib import Path
import subprocess

CONFIG_PATH = Path(__file__).resolve().parent.parent / "credentials.json"


class CredentialError(RuntimeError):
    """A configured credential could not be resolved safely."""


def _settings():
    if not CONFIG_PATH.exists():
        return {}
    try:
        settings = json.loads(CONFIG_PATH.read_text())
        if not isinstance(settings, dict):
            raise ValueError()
        return settings
    except (OSError, ValueError):
        raise CredentialError("Unable to read credentials.json; expected a JSON object.") from None


def has_credential(name):
    """Check configuration without prompting 1Password or retrieving a value."""
    return bool(_settings().get(name) or os.getenv(name))


def get_credential(name, explicit=None):
    """Explicit value > project config > legacy environment variable.

    Configured references fail closed: an op failure never falls back to an
    unrelated environment credential. No subprocess output appears in errors.
    """
    value = explicit if explicit is not None else _settings().get(name, os.getenv(name))
    if value is None:
        return None
    if not isinstance(value, str):
        raise CredentialError(f"Credential {name} must be a string.")
    if not value.startswith("op://"):
        return value
    if len(value[5:].split("/")) < 3 or any(not p for p in value[5:].split("/")):
        raise CredentialError(f"Invalid 1Password reference for {name}.")
    try:
        result = subprocess.run(
            ["op", "read", "--", value],
            capture_output=True, text=True, timeout=30, check=True,
        )
    except (OSError, subprocess.SubprocessError):
        raise CredentialError(
            f"Could not resolve {name} from 1Password. Check op installation, authentication and vault access."
        ) from None
    secret = result.stdout.rstrip("\r\n")
    if not secret:
        raise CredentialError(f"1Password returned an empty value for {name}.")
    return secret
