"""v3.0.0-alpha2: runtime-kind disclosure in ``bytefray agents`` listing.

The Agent Designer's match selectors have decorated every entry with its
runtime kind since RC2 (``claimer [Python]``, ``runner [VM]``), so a user
learns before attempting a match that VM entrants cannot run under Ruleset
v2. The CLI listing showed no such distinction, which mattered more once
the bundled starter set mixed five Python agents with four VM ones. These
tests pin the disclosure and the vocabulary shared with the GUI.

Presentation only: the listing has no JSON/machine-readable form, and no
persisted artifact schema carries a runtime label, so nothing here
constrains a serialized contract.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from battle_engine.agents import agent_runtime_label, discover_agents
from battle_engine.command import main as cli_main
from battle_engine.starters import ensure_starter_agents


def _resource_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture
def data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    ensure_starter_agents(resource_root=_resource_root(), data_root=tmp_path)
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    return tmp_path


def test_listing_labels_python_and_vm_starters(data_root: Path, capsys) -> None:
    assert cli_main(["agents"]) == 0
    lines = capsys.readouterr().out.splitlines()
    labelled = {
        parts[1]: line
        for line in lines
        if line.startswith(" - ") and (parts := line.split())
    }

    for python_agent in ("claimer", "strider", "hunter", "wanderer", "adaptive", "raider", "sentinel"):
        assert "[Python]" in labelled[python_agent], labelled[python_agent]
        assert "[VM]" not in labelled[python_agent]
    for vm_agent in ("runner", "writer", "seeker", "spiral"):
        assert "[VM]" in labelled[vm_agent], labelled[vm_agent]
        assert "[Python]" not in labelled[vm_agent]


def test_listing_explains_which_rulesets_each_runtime_kind_can_use(
    data_root: Path, capsys
) -> None:
    """The legend must state the rule in both directions, and never mention Redcode.

    Redcode/pMARS runs in an external pMARS process under no Bytefray
    Ruleset at all (docs/RULES.md's "Redcode/pMARS -- not Ruleset v1"), so
    naming it beside a Ruleset would teach the exact falsehood this
    disclosure exists to prevent.
    """

    assert cli_main(["agents"]) == 0
    out = capsys.readouterr().out
    assert "[Python] agents run under Ruleset v1 or v2" in out
    assert "[VM] agents run under Ruleset v1 only." in out
    assert "edcode" not in out
    assert "pMARS" not in out


def test_listing_is_pure_ascii(data_root: Path, capsys) -> None:
    """The frozen ``bytefray.exe`` mangles non-ASCII stdout.

    A real, shipped defect this suite exists to prevent recurring: the
    listing previously used an em-dash for "no blob", which the source
    build rendered correctly and the PyInstaller executable rendered as a
    replacement character in the same shell.
    """

    assert cli_main(["agents"]) == 0
    out = capsys.readouterr().out
    assert out.isascii(), f"non-ASCII in agents listing: {out!r}"
    assert "blob=none" in out


def test_runtime_label_matches_the_designers_own_vocabulary(data_root: Path) -> None:
    """One shared spelling, so CLI and GUI never disagree about an agent."""

    from app.services.agent_catalog import AgentCatalog
    from app.services.designer_workflows import agent_runtime_label as designer_label

    specs = discover_agents(data_root)
    rows = {row.agent_id: row for row in AgentCatalog(data_root).list_agents()}
    for agent_id, spec in specs.items():
        engine_label = agent_runtime_label(spec)
        assert engine_label == f"[{designer_label(rows[agent_id])}]"


def test_labelling_follows_the_engines_own_ruleset_v2_restriction(data_root: Path) -> None:
    """``[Python]`` must mean exactly "may execute under Ruleset v2"."""

    from battle_engine.ruleset_policy import RULESET_V2

    for spec in discover_agents(data_root).values():
        allowed = not RULESET_V2.unsupported_runtime_kinds({spec.kind})
        assert (agent_runtime_label(spec) == "[Python]") is allowed
