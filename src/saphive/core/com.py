"""Windows COM runtime helpers used by SAPHive."""

from __future__ import annotations

import sys
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from importlib import import_module
from typing import TypeVar

from saphive.core.errors import ComRuntimeError

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ComRuntime:
    """Guard code that may perform its own COM initialization."""

    enabled: bool = True
    recovery_callbacks: tuple[Callable[[], None], ...] = field(default_factory=tuple)

    def with_recovery_callback(self, callback: Callable[[], None]) -> ComRuntime:
        """Return a runtime that restores external COM state after guarded calls."""
        return ComRuntime(
            enabled=self.enabled,
            recovery_callbacks=(*self.recovery_callbacks, callback),
        )

    def run_with_com_guard(self, callback: Callable[[], T], *, manages_com: bool = True) -> T:
        """Run callback behind an extra COM initialize/uninitialize pair.

        This protects SAPHive's outer COM apartment from libraries that manage
        COM internally, as long as those libraries balance their own COM calls.
        """
        if not manages_com or not self.enabled or sys.platform != "win32":
            return self._run_and_recover(callback)

        pythoncom = _load_pythoncom()
        try:
            pythoncom.CoInitialize()
        except Exception as exc:
            raise ComRuntimeError(
                "SAPHive could not initialize a guarded Windows COM boundary.",
                details={"error": str(exc)},
            ) from exc

        try:
            return self._run_and_recover(callback)
        finally:
            try:
                pythoncom.CoUninitialize()
            except Exception as exc:
                raise ComRuntimeError(
                    "SAPHive could not release a guarded Windows COM boundary.",
                    details={"error": str(exc)},
                ) from exc

    def _run_and_recover(self, callback: Callable[[], T]) -> T:
        primary_error: BaseException | None = None
        try:
            result = callback()
        except BaseException as exc:
            primary_error = exc
            raise
        finally:
            if primary_error is None:
                self.recover_external_state()
            else:
                with suppress(Exception):
                    self.recover_external_state()

        return result

    def recover_external_state(self) -> None:
        """Refresh external COM proxies after another library used COM."""
        for callback in self.recovery_callbacks:
            try:
                callback()
            except Exception as exc:
                raise ComRuntimeError(
                    "SAPHive could not recover external COM state after a guarded call.",
                    details={"error": str(exc), "error_type": type(exc).__name__},
                ) from exc


def _load_pythoncom():
    try:
        return import_module("pythoncom")
    except ImportError as exc:
        raise ComRuntimeError(
            "Windows COM support requires pywin32 on Windows.",
            details={"missing_dependency": "pywin32"},
        ) from exc
