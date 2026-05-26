"""Windows COM runtime helpers used by SAPHive."""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from typing import Any, TypeVar

from saphive.core.errors import ComRuntimeError

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ComRuntime:
    """Guard code that may perform its own COM initialization."""

    enabled: bool = True

    def run_with_com_guard(self, callback: Callable[[], T], *, manages_com: bool = True) -> T:
        """Run callback behind an extra COM initialize/uninitialize pair.

        Use this for explicit COM boundaries only. SAPHive does not recover or
        rebind SAP GUI proxies after external COM owners run.
        """
        if not manages_com or not self.enabled or sys.platform != "win32":
            return callback()

        pythoncom = _load_pythoncom()
        try:
            pythoncom.CoInitialize()
        except Exception as exc:
            raise ComRuntimeError(
                "SAPHive could not initialize a guarded Windows COM boundary.",
                details={"error": str(exc)},
            ) from exc

        try:
            return callback()
        finally:
            try:
                pythoncom.CoUninitialize()
            except Exception as exc:
                raise ComRuntimeError(
                    "SAPHive could not release a guarded Windows COM boundary.",
                    details={"error": str(exc)},
                ) from exc


def _load_pythoncom() -> Any:
    try:
        return import_module("pythoncom")
    except ImportError as exc:
        raise ComRuntimeError(
            "Windows COM support requires pywin32 on Windows.",
            details={"missing_dependency": "pywin32"},
        ) from exc
