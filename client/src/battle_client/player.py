"""Replay iteration and renderer lifecycle orchestration."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from battle_engine.replay import ReplayRecord

from battle_client.renderers.base import AbstractRenderer


class ReplayPlayer:
    """Deliver replay records through one explicit renderer lifecycle."""

    def __init__(self, renderer: AbstractRenderer):
        self.renderer = renderer

    def play(
        self,
        records: Iterable[ReplayRecord],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        renderer = self.renderer
        try:
            renderer.setup(metadata)
            renderer.wait_for_start()

            # Keep iteration here, separate from presentation. A one-record
            # lookahead lets completion be detected without blocking a paused
            # interactive renderer after the final record.
            iterator = iter(records)
            try:
                pending = next(iterator)
            except StopIteration:
                pending = None

            while pending is not None:
                renderer.wait_until_ready()
                renderer.on_event(pending)
                renderer.update()
                try:
                    pending = next(iterator)
                except StopIteration:
                    pending = None

            renderer.on_complete()
            renderer.hold_open()
        finally:
            renderer.teardown()
