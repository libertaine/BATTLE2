"""Shared pMARS executable discovery, invocation, and error normalization."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from battle_engine.paths import get_data_root, get_resource_root, normalize_root

DEFAULT_TIMEOUT_SECONDS = 30.0


class PMarsError(RuntimeError):
    """Base class for errors safe to display in CLI and GUI surfaces."""

    def __init__(self, message: str, *, exit_code: int = 2) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class PMarsNotFoundError(PMarsError):
    """Raised when no usable pMARS executable can be resolved."""


class PMarsExecutionError(PMarsError):
    """Raised when pMARS starts but exits unsuccessfully."""

    def __init__(
        self,
        message: str,
        *,
        returncode: int,
        stdout: str = "",
        stderr: str = "",
    ) -> None:
        super().__init__(message, exit_code=returncode if 0 < returncode < 256 else 1)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class PMarsTimeoutError(PMarsError):
    """Raised when pMARS exceeds its configured execution timeout."""

    def __init__(self, message: str, *, stdout: str = "", stderr: str = "") -> None:
        super().__init__(message, exit_code=124)
        self.stdout = stdout
        self.stderr = stderr


class PMarsOutputError(PMarsError):
    """Raised when successful pMARS output has no supported result."""

    def __init__(self, message: str, *, stdout: str = "", stderr: str = "") -> None:
        super().__init__(message)
        self.stdout = stdout
        self.stderr = stderr


@dataclass(frozen=True)
class PMarsResult:
    """Successful normalized pMARS process result."""

    command: tuple[str, ...]
    winner: str
    returncode: int
    stdout: str
    stderr: str


def _executable_names() -> tuple[str, ...]:
    return ("pmars.exe", "pmars") if os.name == "nt" else ("pmars", "pmars.exe")


def _candidate_directories(resource_root: Path, data_root: Path) -> list[Path]:
    directories = [
        resource_root / "pmars" / "windows",
        resource_root / "pmars",
        data_root / "pmars" / "windows",
        data_root / "pmars",
        data_root / "bin",
    ]
    result: list[Path] = []
    for directory in directories:
        normalized = normalize_root(directory)
        if normalized not in result:
            result.append(normalized)
    return result


def _resolve_file_or_path_command(value: str) -> Path | None:
    candidate = Path(value).expanduser()
    if candidate.is_file():
        return candidate.resolve()
    found = shutil.which(value)
    return Path(found).resolve() if found else None


def resolve_pmars_command(
    *,
    environ: Mapping[str, str] | None = None,
    resource_root: Path | None = None,
    data_root: Path | None = None,
) -> list[str]:
    """Resolve pMARS according to explicit, packaged, installed, source, then PATH order."""
    env = os.environ if environ is None else environ
    explicit = env.get("PMARS_CMD", "").strip()
    if explicit:
        # A surrounding quote pair is accepted for compatibility with common
        # Windows environment-variable configuration. Fixed arguments are not
        # split: PMARS_CMD has historically represented one executable.
        value = explicit[1:-1] if len(explicit) >= 2 and explicit[0] == explicit[-1] == '"' else explicit
        resolved = _resolve_file_or_path_command(value)
        if resolved is None:
            raise PMarsNotFoundError(
                f"Configured PMARS_CMD executable was not found: {explicit!r}. "
                "Correct or unset PMARS_CMD; explicit configuration does not fall back."
            )
        return [str(resolved)]

    resources = get_resource_root() if resource_root is None else normalize_root(resource_root)
    writable = get_data_root(environ) if data_root is None else normalize_root(data_root)
    searched: list[Path] = []
    for directory in _candidate_directories(resources, writable):
        for name in _executable_names():
            candidate = (directory / name).resolve()
            searched.append(candidate)
            if candidate.is_file():
                return [str(candidate)]

    for name in _executable_names():
        found = shutil.which(name)
        if found:
            return [str(Path(found).resolve())]

    locations = "\n  - ".join(str(path) for path in searched)
    path_names = ", ".join(_executable_names())
    raise PMarsNotFoundError(
        "pMARS executable was not found. Set PMARS_CMD to its executable path, "
        f"install it in one of these locations:\n  - {locations}\n"
        f"or make one of [{path_names}] available through PATH."
    )


def _diagnostic_context(stdout: str, stderr: str) -> str:
    detail = stderr.strip() or stdout.strip()
    if not detail:
        return "no process output"
    return detail[-1000:]


def parse_pmars_winner(stdout: str) -> str:
    """Parse supported pMARS batch result formats or raise a normalized error."""
    if re.search(r"\bA\s+wins\b", stdout, re.IGNORECASE):
        return "A"
    if re.search(r"\bB\s+wins\b", stdout, re.IGNORECASE):
        return "B"
    if re.search(r"\b(?:tie|draw)\b", stdout, re.IGNORECASE):
        return "tie"

    results = re.search(r"^Results:\s*(\d+)\s+(\d+)\s+(\d+)\s*$", stdout, re.MULTILINE | re.IGNORECASE)
    if results:
        a_wins, b_wins = int(results.group(1)), int(results.group(2))
        return "A" if a_wins > b_wins else "B" if b_wins > a_wins else "tie"

    labeled = re.search(r"A\s*[:=]\s*(\d+).+?B\s*[:=]\s*(\d+)", stdout, re.DOTALL)
    if labeled:
        a_score, b_score = int(labeled.group(1)), int(labeled.group(2))
        return "A" if a_score > b_score else "B" if b_score > a_score else "tie"

    scores = re.findall(r"^.+?\s+scores\s+(-?\d+)\s*$", stdout, re.MULTILINE | re.IGNORECASE)
    if len(scores) >= 2:
        a_score, b_score = int(scores[0]), int(scores[1])
        return "A" if a_score > b_score else "B" if b_score > a_score else "tie"

    raise PMarsOutputError(
        "pMARS exited successfully but its result could not be parsed. "
        f"Output: {_diagnostic_context(stdout, '')}",
        stdout=stdout,
    )


def run_pmars(
    arguments: Sequence[str],
    *,
    command: Sequence[str] | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    environ: Mapping[str, str] | None = None,
) -> PMarsResult:
    """Resolve and run pMARS without a shell, normalizing all process failures."""
    resolved = list(command) if command is not None else resolve_pmars_command(environ=environ)
    if not resolved:
        raise PMarsNotFoundError("The resolved pMARS command is empty.")
    process_command = [*map(str, resolved), *map(str, arguments)]
    try:
        completed = subprocess.run(
            process_command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise PMarsNotFoundError(
            f"pMARS executable could not be started: {process_command[0]}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        raise PMarsTimeoutError(
            f"pMARS timed out after {timeout:g} seconds. "
            f"Output: {_diagnostic_context(stdout, stderr)}",
            stdout=stdout,
            stderr=stderr,
        ) from exc
    except OSError as exc:
        raise PMarsExecutionError(
            f"pMARS could not be started: {process_command[0]}: {exc}", returncode=1
        ) from exc

    if completed.returncode != 0:
        raise PMarsExecutionError(
            f"pMARS exited with code {completed.returncode}. "
            f"Output: {_diagnostic_context(completed.stdout, completed.stderr)}",
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    try:
        winner = parse_pmars_winner(completed.stdout)
    except PMarsOutputError as exc:
        exc.stderr = completed.stderr
        raise
    return PMarsResult(
        command=tuple(process_command),
        winner=winner,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )
