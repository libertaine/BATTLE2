"""Canonical ``battle2.result`` v1 models, serialization, and compatibility output."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

SCHEMA_NAME = "battle2.result"
SCHEMA_VERSION = 1


def canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def stable_id(prefix: str, value: Mapping[str, Any]) -> str:
    return f"{prefix}_{hashlib.sha256(canonical_json(value)).hexdigest()[:24]}"


@dataclass(frozen=True)
class ReplayReference:
    replay_id: str
    sha256: str
    filename: str


@dataclass(frozen=True)
class ResultEnvelope:
    result_id: str
    match_id: str
    mode: str
    winner: str
    termination_reason: str
    ticks: int
    score: Mapping[str, int | float] = field(default_factory=dict)
    entrants: tuple[Mapping[str, Any], ...] = ()
    reproducibility: Mapping[str, Any] = field(default_factory=dict)
    replay: ReplayReference | None = None
    backend: Mapping[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_NAME,
            "schema_version": SCHEMA_VERSION,
            "result_id": self.result_id,
            "match_id": self.match_id,
            "mode": self.mode,
            "status": "completed",
            "winner": self.winner,
            "termination_reason": self.termination_reason,
            "ticks": self.ticks,
            "score": dict(self.score),
            "entrants": [dict(entrant) for entrant in self.entrants],
            "reproducibility": dict(self.reproducibility),
            "replay": (
                None
                if self.replay is None
                else {
                    "replay_id": self.replay.replay_id,
                    "sha256": self.replay.sha256,
                    "filename": self.replay.filename,
                }
            ),
            "backend": None if self.backend is None else dict(self.backend),
        }


def write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(json.dumps(value, indent=2, sort_keys=True).encode("utf-8"))
            stream.write(b"\n")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def read_result(path: str | Path) -> ResultEnvelope:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema") != SCHEMA_NAME or data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported battle2.result schema")
    replay = data.get("replay")
    return ResultEnvelope(
        result_id=data["result_id"],
        match_id=data["match_id"],
        mode=data["mode"],
        winner=data["winner"],
        termination_reason=data["termination_reason"],
        ticks=int(data["ticks"]),
        score=data.get("score", {}),
        entrants=tuple(data.get("entrants", ())),
        reproducibility=data.get("reproducibility", {}),
        replay=(
            None
            if replay is None
            else ReplayReference(replay["replay_id"], replay["sha256"], replay["filename"])
        ),
        backend=data.get("backend"),
    )


class ReplayIntegrityError(ValueError):
    """A result's referenced replay is missing, unreadable, or digest-mismatched.

    Raised only by explicit verification calls (``verify_replay_digest``,
    ``verify_result_replay``) -- ``read_result`` itself never verifies the
    referenced replay, so reading historical results stays unaffected by
    this check unless a caller opts in at a canonical-artifact boundary.
    """

    def __init__(self, message: str, *, code: str):
        super().__init__(message)
        self.code = code


def verify_replay_digest(result: ResultEnvelope, replay_path: str | Path) -> str:
    """Verify ``replay_path`` matches the digest recorded on ``result``.

    Returns the recomputed digest on success. Raises ``ReplayIntegrityError``
    (with a stable ``code``) if the result has no replay reference, the file
    is missing or unreadable, or its digest does not match.
    """

    if result.replay is None:
        raise ReplayIntegrityError(
            "Result has no replay reference to verify (e.g. a pMARS match).",
            code="replay_reference_missing",
        )
    path = Path(replay_path)
    if not path.is_file():
        raise ReplayIntegrityError(
            f"Referenced replay file does not exist: {path}",
            code="replay_file_missing",
        )
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ReplayIntegrityError(
            f"Referenced replay file could not be read: {path}: {exc}",
            code="replay_file_unreadable",
        ) from exc
    if digest != result.replay.sha256:
        raise ReplayIntegrityError(
            f"Replay digest mismatch for {path}: "
            f"expected {result.replay.sha256}, got {digest}",
            code="replay_digest_mismatch",
        )
    return digest


def verify_result_replay(path: str | Path) -> str:
    """Read a ``result.json`` at ``path`` and verify its replay's digest.

    The replay is resolved relative to ``path``'s parent directory, matching
    how ``ReplayReference.filename`` is always a bare, portable filename
    rather than an absolute path (see ``ReplayReference``).
    """

    result_path = Path(path)
    envelope = read_result(result_path)
    if envelope.replay is None:
        raise ReplayIntegrityError(
            "Result has no replay reference to verify (e.g. a pMARS match).",
            code="replay_reference_missing",
        )
    return verify_replay_digest(envelope, result_path.parent / envelope.replay.filename)
