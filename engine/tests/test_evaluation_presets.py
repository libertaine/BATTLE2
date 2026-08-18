"""v1.6 Phase 3 -- evaluation preset schema, storage, and CLI
(docs/V1_6_PHASE3_EVALUATION_PRESETS.md).

Covers preset loading/validation (schema/version/type/unknown-field
strictness), path-safety (traversal, absolute injection, ambiguous
duplicate names), and the ``list``/``show``/``validate`` CLI surface.
Resolution-layering, canonical-identity, orientation, parallel-composition,
and resume-authority coverage lives in
``test_agent_evaluation_presets.py`` (it needs the full ``agent_evaluation``
CLI, not just this module in isolation).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from battle_engine.agent_evaluation import (
    ORIENTATION_MODE_BOTH,
    ORIENTATION_MODE_CANDIDATE_FIRST_ONLY,
)
from battle_engine.evaluation_presets import (
    ORIENTATION_BOTH,
    ORIENTATION_CANDIDATE_FIRST_ONLY,
    SCHEMA_NAME,
    SCHEMA_VERSION,
    EvaluationPresetError,
    list_presets,
    load_preset,
    load_preset_file,
    presets_root,
    resolve_preset_path,
)
from battle_engine.evaluation_presets import (
    main as presets_main,
)


def _write_preset(root: Path, name: str, body: dict | None, *, ext: str = ".yaml") -> Path:
    import yaml

    directory = presets_root(root)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}{ext}"
    payload = {"schema": SCHEMA_NAME, "schema_version": SCHEMA_VERSION}
    if body:
        payload.update(body)
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Orientation vocabulary pinned equal (Sec: avoid a circular import while
# still reusing the exact same string values agent_evaluation defines).
# ---------------------------------------------------------------------------


def test_orientation_vocabulary_matches_agent_evaluation():
    assert ORIENTATION_BOTH == ORIENTATION_MODE_BOTH
    assert ORIENTATION_CANDIDATE_FIRST_ONLY == ORIENTATION_MODE_CANDIDATE_FIRST_ONLY


# ---------------------------------------------------------------------------
# Schema / parsing
# ---------------------------------------------------------------------------


def test_valid_preset_loads_every_field(tmp_path):
    _write_preset(
        tmp_path,
        "standard",
        {
            "description": "Standard interactive matrix.",
            "candidate": "cand",
            "baseline": "base",
            "opponents": ["opp_a", "opp_b"],
            "seeds": [1, 2, 3],
            "ticks": 200,
            "orientation": "both",
        },
    )
    preset = load_preset(tmp_path, "standard")
    assert preset.name == "standard"
    assert preset.description == "Standard interactive matrix."
    assert preset.candidate_id == "cand"
    assert preset.baseline_id == "base"
    assert preset.opponent_ids == ("opp_a", "opp_b")
    assert preset.seeds == (1, 2, 3)
    assert preset.seed_range is None
    assert preset.ticks == 200
    assert preset.orientation == "both"
    assert preset.content_digest.startswith("evaluation-preset_")


def test_minimal_preset_all_optional_fields_none(tmp_path):
    _write_preset(tmp_path, "minimal", {})
    preset = load_preset(tmp_path, "minimal")
    assert preset.candidate_id is None
    assert preset.baseline_id is None
    assert preset.opponent_ids is None
    assert preset.seeds is None
    assert preset.seed_range is None
    assert preset.ticks is None
    assert preset.orientation is None


def test_seed_range_field(tmp_path):
    _write_preset(tmp_path, "ranged", {"seed_range": {"start": 10, "end": 15}})
    preset = load_preset(tmp_path, "ranged")
    assert preset.seed_range == (10, 15)
    assert preset.seeds is None


def test_malformed_yaml_rejected(tmp_path):
    directory = presets_root(tmp_path)
    directory.mkdir(parents=True)
    (directory / "broken.yaml").write_text("schema: [unterminated", encoding="utf-8")
    with pytest.raises(EvaluationPresetError, match="malformed YAML"):
        load_preset(tmp_path, "broken")


def test_non_mapping_root_rejected(tmp_path):
    directory = presets_root(tmp_path)
    directory.mkdir(parents=True)
    (directory / "list.yaml").write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(EvaluationPresetError, match="mapping"):
        load_preset(tmp_path, "list")


def test_wrong_schema_string_rejected(tmp_path):
    directory = presets_root(tmp_path)
    directory.mkdir(parents=True)
    (directory / "wrong.yaml").write_text(
        "schema: bytefray.evaluation\nschema_version: 1\n", encoding="utf-8"
    )
    with pytest.raises(EvaluationPresetError, match="'schema'"):
        load_preset(tmp_path, "wrong")


def test_unsupported_schema_version_rejected(tmp_path):
    _write_preset(tmp_path, "future", {"schema_version": 999})
    with pytest.raises(EvaluationPresetError, match="schema_version"):
        load_preset(tmp_path, "future")


def test_missing_required_fields_rejected(tmp_path):
    directory = presets_root(tmp_path)
    directory.mkdir(parents=True)
    (directory / "noschema.yaml").write_text("candidate: cand\n", encoding="utf-8")
    with pytest.raises(EvaluationPresetError, match="missing required"):
        load_preset(tmp_path, "noschema")


@pytest.mark.parametrize(
    "field,value",
    [
        ("candidate", 5),
        ("baseline", 5),
        ("description", 5),
        ("opponents", "not_a_list"),
        ("opponents", [1, 2]),
        ("seeds", "1,2,3"),
        ("seeds", ["a", "b"]),
        ("seeds", [1, True]),
        ("ticks", "200"),
        ("ticks", 0),
        ("ticks", -5),
        ("orientation", "sideways"),
        ("orientation", 1),
    ],
)
def test_invalid_field_types_rejected(tmp_path, field, value):
    _write_preset(tmp_path, "bad", {field: value})
    with pytest.raises(EvaluationPresetError):
        load_preset(tmp_path, "bad")


def test_empty_opponents_and_seeds_lists_are_type_valid(tmp_path):
    """Sec 6: schema loading is a type check only -- non-emptiness is a
    business rule the reused EvaluationRequest validation path enforces
    after resolution, not a rule duplicated here. See
    test_agent_evaluation_presets.py for the end-to-end behavior."""

    _write_preset(tmp_path, "empties", {"opponents": [], "seeds": []})
    preset = load_preset(tmp_path, "empties")
    assert preset.opponent_ids == ()
    assert preset.seeds == ()


def test_unknown_top_level_field_rejected(tmp_path):
    _write_preset(tmp_path, "extra", {"workers": 4})
    with pytest.raises(EvaluationPresetError, match="unknown field"):
        load_preset(tmp_path, "extra")


def test_seeds_and_seed_range_mutually_exclusive(tmp_path):
    _write_preset(tmp_path, "both", {"seeds": [1, 2], "seed_range": {"start": 1, "end": 2}})
    with pytest.raises(EvaluationPresetError, match="mutually exclusive"):
        load_preset(tmp_path, "both")


def test_seed_range_end_before_start_rejected(tmp_path):
    _write_preset(tmp_path, "backwards", {"seed_range": {"start": 10, "end": 1}})
    with pytest.raises(EvaluationPresetError, match="end.*start"):
        load_preset(tmp_path, "backwards")


def test_seed_range_wrong_shape_rejected(tmp_path):
    _write_preset(tmp_path, "shape", {"seed_range": {"start": 1}})
    with pytest.raises(EvaluationPresetError, match="seed_range"):
        load_preset(tmp_path, "shape")


# ---------------------------------------------------------------------------
# Path / name safety
# ---------------------------------------------------------------------------


def test_unknown_preset_name_raises(tmp_path):
    with pytest.raises(EvaluationPresetError, match="Unknown evaluation preset"):
        load_preset(tmp_path, "nope")


def test_path_traversal_rejected(tmp_path):
    with pytest.raises(EvaluationPresetError):
        resolve_preset_path(tmp_path, "../escape")


@pytest.mark.parametrize("name", ["../x", "a/b", "a\\b", "", "   ", ".hidden", "-dash-first"])
def test_unsafe_names_rejected(tmp_path, name):
    with pytest.raises(EvaluationPresetError):
        resolve_preset_path(tmp_path, name)


def test_absolute_path_injection_rejected(tmp_path):
    outside = tmp_path.parent / "outside_secret.yaml"
    outside.write_text("schema: bytefray.evaluation_preset\nschema_version: 1\n", encoding="utf-8")
    # An absolute-path-shaped "name" must never escape the presets root --
    # rejected as an invalid name before any file lookup occurs.
    with pytest.raises(EvaluationPresetError):
        resolve_preset_path(tmp_path, str(outside))


def test_duplicate_ambiguous_extension_names_rejected(tmp_path):
    _write_preset(tmp_path, "dup", {}, ext=".yaml")
    _write_preset(tmp_path, "dup", {}, ext=".yml")
    with pytest.raises(EvaluationPresetError, match="Ambiguous"):
        load_preset(tmp_path, "dup")


def test_list_presets_deduplicates_and_sorts(tmp_path):
    _write_preset(tmp_path, "zeta", {})
    _write_preset(tmp_path, "alpha", {})
    assert list_presets(tmp_path) == ("alpha", "zeta")


def test_list_presets_empty_root_returns_empty_tuple(tmp_path):
    assert list_presets(tmp_path) == ()


def test_content_digest_independent_of_filename(tmp_path):
    """Sec 7: two identically-configured, differently-named presets must
    produce the same content digest -- the digest never hashes the name/path."""

    body = {"candidate": "cand", "opponents": ["opp"], "seeds": [1]}
    _write_preset(tmp_path, "name_a", body)
    _write_preset(tmp_path, "name_b", body)
    preset_a = load_preset(tmp_path, "name_a")
    preset_b = load_preset(tmp_path, "name_b")
    assert preset_a.content_digest == preset_b.content_digest


def test_content_digest_changes_with_content(tmp_path):
    _write_preset(tmp_path, "one", {"opponents": ["opp_a"]})
    _write_preset(tmp_path, "two", {"opponents": ["opp_b"]})
    assert load_preset(tmp_path, "one").content_digest != load_preset(tmp_path, "two").content_digest


def test_load_preset_file_accepts_explicit_path(tmp_path):
    path = _write_preset(tmp_path, "direct", {"candidate": "cand"})
    preset = load_preset_file(path)
    assert preset.name == "direct"
    assert preset.candidate_id == "cand"


# ---------------------------------------------------------------------------
# CLI: list / show / validate
# ---------------------------------------------------------------------------


def test_cli_list_empty(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    exit_code = presets_main(["list"])
    assert exit_code == 0
    assert "No evaluation presets found" in capsys.readouterr().out


def test_cli_list_shows_names_and_descriptions(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    _write_preset(tmp_path, "standard", {"description": "The standard matrix."})
    _write_preset(tmp_path, "smoke", {})
    exit_code = presets_main(["list"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "smoke" in out
    assert "standard" in out
    assert "The standard matrix." in out


def test_cli_list_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    _write_preset(tmp_path, "standard", {})
    exit_code = presets_main(["list", "--json"])
    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert data == {"presets": ["standard"]}


def test_cli_show_plain(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    _write_preset(
        tmp_path,
        "standard",
        {"candidate": "cand", "opponents": ["opp"], "seeds": [1, 2], "ticks": 150, "orientation": "both"},
    )
    exit_code = presets_main(["show", "standard"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "candidate: cand" in out
    assert "opponents: opp" in out
    assert "seeds: 1, 2" in out
    assert "ticks: 150" in out
    assert "orientation: both" in out
    assert "content_digest" in out


def test_cli_show_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    _write_preset(tmp_path, "standard", {"candidate": "cand"})
    exit_code = presets_main(["show", "standard", "--json"])
    assert exit_code == 0
    data = json.loads(capsys.readouterr().out)
    assert data["name"] == "standard"
    assert data["candidate"] == "cand"
    assert data["schema"] == SCHEMA_NAME
    assert data["schema_version"] == SCHEMA_VERSION


def test_cli_show_unknown_preset_exits_2(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    exit_code = presets_main(["show", "nope"])
    assert exit_code == 2
    assert "ERROR" in capsys.readouterr().err


def test_cli_validate_valid_preset(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    _write_preset(tmp_path, "standard", {"candidate": "cand"})
    exit_code = presets_main(["validate", "standard"])
    assert exit_code == 0
    assert "OK" in capsys.readouterr().out


def test_cli_validate_invalid_preset_exits_1(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    _write_preset(tmp_path, "bad", {"ticks": -1})
    exit_code = presets_main(["validate", "bad"])
    assert exit_code == 1
    assert "INVALID" in capsys.readouterr().err


def test_cli_dispatch_via_command_module(tmp_path, monkeypatch, capsys):
    """The 'bytefray agents evaluation-presets ...' dispatch path (command.py)."""

    from battle_engine.command import _agents

    monkeypatch.setenv("BYTEFRAY_ROOT", str(tmp_path))
    _write_preset(tmp_path, "standard", {})
    exit_code = _agents(["evaluation-presets", "list"])
    assert exit_code == 0
    assert "standard" in capsys.readouterr().out
