"""Utilities for explicit monkey-patch lifecycle management."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class ManagedPatch:
    patch_id: str
    apply: Callable[[], None]
    restore: Callable[[], None]
    is_applied: Callable[[], bool]


class PatchRegistry:
    """Small registry that makes runtime patches idempotent and restorable."""

    def __init__(self) -> None:
        self._patches: dict[str, ManagedPatch] = {}

    def register(self, patch: ManagedPatch) -> None:
        self._patches[patch.patch_id] = patch

    def apply(self, patch_id: str) -> None:
        patch = self._patches[patch_id]
        if not patch.is_applied():
            patch.apply()

    def restore(self, patch_id: str) -> None:
        patch = self._patches[patch_id]
        if patch.is_applied():
            patch.restore()

    def apply_all(self) -> None:
        for patch in self._patches.values():
            if not patch.is_applied():
                patch.apply()

    def restore_all(self) -> None:
        for patch in reversed(list(self._patches.values())):
            if patch.is_applied():
                patch.restore()

    def is_applied(self, patch_id: str) -> bool:
        return self._patches[patch_id].is_applied()
