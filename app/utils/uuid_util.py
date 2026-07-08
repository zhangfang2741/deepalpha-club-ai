"""Deterministic UUID helpers."""

import hashlib
import uuid


def generate_uuid_from_str(value: str) -> str:
    """Return a stable UUID derived from arbitrary text."""
    digest = hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()
    return str(uuid.UUID(digest[:32]))
