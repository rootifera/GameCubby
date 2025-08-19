# gamecubby_api/utils/maintenance.py
"""
Lightweight utilities for application maintenance mode.

This module centralizes the logic around a shared JSON flag file so both
the API and the Web UI can coordinate maintenance without depending on
the database state.

Default file path can be overridden with env var GC_MAINT_FILE.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Mapping, MutableMapping, Optional

DEFAULT_MAINT_FILE = "/storage/maintenance.json"

DEFAULT_ALLOW_PREFIXES: tuple[str, ...] = (
    "/admin/maintenance/",
    "/health",
)


@dataclass(frozen=True)
class MaintenanceStatus:
    enabled: bool
    reason: Optional[str] = None
    by: Optional[str] = None
    started_at: Optional[str] = None  # ISO8601
    allow: Optional[List[str]] = None
    nonce: Optional[str] = None

    @staticmethod
    def disabled() -> "MaintenanceStatus":
        return MaintenanceStatus(enabled=False)


def _maint_file_path() -> str:
    """
    Resolve the maintenance JSON file path from environment or defaults.
    """
    return os.getenv("GC_MAINT_FILE", DEFAULT_MAINT_FILE)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_maintenance() -> MaintenanceStatus:
    """
    Read the maintenance JSON file. If missing or unreadable, returns disabled.
    """
    path = _maint_file_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        return MaintenanceStatus.disabled()
    except Exception:
        return MaintenanceStatus.disabled()

    if not isinstance(raw, Mapping):
        return MaintenanceStatus.disabled()

    allow = raw.get("allow")
    allow_list = list(allow) if isinstance(allow, Iterable) and not isinstance(allow, (str, bytes)) else None

    return MaintenanceStatus(
        enabled=bool(raw.get("enabled", False)),
        reason=(raw.get("reason") if isinstance(raw.get("reason"), str) else None),
        by=(raw.get("by") if isinstance(raw.get("by"), str) else None),
        started_at=(raw.get("started_at") if isinstance(raw.get("started_at"), str) else None),
        allow=allow_list,
        nonce=(raw.get("nonce") if isinstance(raw.get("nonce"), str) else None),
    )


def is_maintenance_enabled() -> bool:
    """
    Convenience wrapper to check current enabled state.
    """
    return read_maintenance().enabled


def allowed_in_maintenance(path: str, extra_allow_prefixes: Optional[Iterable[str]] = None) -> bool:
    """
    Decide whether a request path should be allowed to pass during maintenance.
    """
    prefixes = list(DEFAULT_ALLOW_PREFIXES)
    if extra_allow_prefixes:
        for p in extra_allow_prefixes:
            if isinstance(p, str) and p:
                prefixes.append(p)
    return any(path.startswith(p) for p in prefixes)


def _write_json(obj: MutableMapping[str, object]) -> None:
    """
    Write the given object to the maintenance JSON file (creates parent dirs).
    """
    path = _maint_file_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)


def enter_maintenance(
        *,
        reason: str = "restore",
        by: str = "api",
        allow_prefixes: Optional[Iterable[str]] = None,
        nonce: Optional[str] = None,
) -> MaintenanceStatus:
    """
    Enable maintenance mode (idempotent).

    - Writes/overwrites the JSON flag with provided metadata.
    - Returns the effective MaintenanceStatus after the write.
    """
    current = read_maintenance()
    if current.enabled:
        return current

    allow = list(DEFAULT_ALLOW_PREFIXES)
    if allow_prefixes:
        for p in allow_prefixes:
            if isinstance(p, str) and p and p not in allow:
                allow.append(p)

    data: MutableMapping[str, object] = {
        "enabled": True,
        "reason": reason,
        "by": by,
        "started_at": _utcnow_iso(),
        "allow": allow,
    }
    if nonce:
        data["nonce"] = nonce

    _write_json(data)
    return read_maintenance()


def exit_maintenance() -> MaintenanceStatus:
    """
    Disable maintenance mode (idempotent). Deletes the JSON file if present.
    """
    path = _maint_file_path()
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except Exception:
        _write_json({"enabled": False})
    return MaintenanceStatus.disabled()


def get_status_dict() -> dict:
    """
    Return a dict suitable for API responses (no exceptions).
    """
    st = read_maintenance()
    return {
        "enabled": st.enabled,
        "reason": st.reason,
        "by": st.by,
        "started_at": st.started_at,
        "allow": st.allow or list(DEFAULT_ALLOW_PREFIXES),
    }
