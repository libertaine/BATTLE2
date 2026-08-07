from __future__ import annotations

import json
from pathlib import Path

import pytest
from battle_engine.agent_api import (
    AgentContractError,
    AgentFactoryError,
    AgentImportError,
    AgentManifestError,
    AgentSourceError,
    UnsupportedAgentAPIVersionError,
    load_python_agent,
)
from battle_engine.agents import discover_agents, resolve_agent

VALID_SOURCE = """
class ExampleAgent:
    def __init__(self):
        self.origin = __file__

    def reset(self, context):
        self.context = context

    def act(self, observation):
        return None

def create_agent():
    return ExampleAgent()
"""


def _write_agent(
    root: Path,
    folder: str = "example",
    *,
    manifest: dict[str, object] | None = None,
    source: str | None = VALID_SOURCE,
) -> Path:
    directory = root / "agents" / folder
    directory.mkdir(parents=True)
    values = {
        "api_version": 1,
        "kind": "python",
        "entrypoint": "agent.py:create_agent",
        "name": folder,
        "display": f"{folder.title()} Agent",
        "version": "1.0.0",
    }
    if manifest:
        values.update(manifest)
    (directory / "agent.yaml").write_text(json.dumps(values), encoding="utf-8")
    if source is not None:
        (directory / "agent.py").write_text(source, encoding="utf-8")
    return directory


def test_valid_python_agent_is_discovered_loaded_and_fresh(tmp_path):
    directory = _write_agent(tmp_path)

    spec = resolve_agent(tmp_path, "example")
    first = load_python_agent(spec)
    second = load_python_agent(spec)

    assert spec.kind == "python"
    assert spec.api_version == 1
    assert spec.version == "1.0.0"
    assert spec.source_path == directory / "agent.py"
    assert spec.entry_point == "agent.py:create_agent"
    assert first.instance is not second.instance
    assert first.metadata.agent_id == "example"
    assert first.metadata.name == "Example Agent"
    assert first.metadata.version == "1.0.0"
    assert first.source_path == directory / "agent.py"


def test_unsupported_api_version_has_typed_diagnostic(tmp_path):
    _write_agent(tmp_path, manifest={"api_version": 2})

    with pytest.raises(UnsupportedAgentAPIVersionError) as caught:
        load_python_agent(resolve_agent(tmp_path, "example"))

    assert caught.value.code == "agent_api_version_unsupported"
    assert "supports version 1" in str(caught.value)


@pytest.mark.parametrize(
    ("manifest", "message"),
    [
        ({"api_version": "1"}, "api_version"),
        ({"kind": "extension"}, "kind"),
        ({"entrypoint": []}, "entrypoint"),
        ({"version": ""}, "version"),
        ({"defaults": []}, "defaults"),
    ],
)
def test_malformed_manifest_has_typed_diagnostic(tmp_path, manifest, message):
    _write_agent(tmp_path, manifest=manifest)

    with pytest.raises(AgentManifestError) as caught:
        discover_agents(tmp_path)

    assert caught.value.code == "agent_manifest_invalid"
    assert message in str(caught.value)


def test_unparseable_manifest_has_typed_diagnostic(tmp_path):
    directory = tmp_path / "agents" / "broken"
    directory.mkdir(parents=True)
    (directory / "agent.yaml").write_text("kind: [python", encoding="utf-8")

    with pytest.raises(AgentManifestError) as caught:
        discover_agents(tmp_path)

    assert caught.value.code == "agent_manifest_invalid"
    assert str(directory / "agent.yaml") in str(caught.value)


def test_missing_python_source_file(tmp_path):
    _write_agent(tmp_path, source=None)

    with pytest.raises(AgentSourceError, match="was not found"):
        load_python_agent(resolve_agent(tmp_path, "example"))


def test_python_syntax_error_is_normalized(tmp_path):
    _write_agent(tmp_path, source="def create_agent(:\n    pass\n")

    with pytest.raises(AgentImportError) as caught:
        load_python_agent(resolve_agent(tmp_path, "example"))

    assert caught.value.code == "agent_import_failed"
    assert "SyntaxError" in str(caught.value)


def test_import_time_exception_is_normalized(tmp_path):
    _write_agent(tmp_path, source="raise RuntimeError('import exploded')\n")

    with pytest.raises(AgentImportError, match="RuntimeError: import exploded"):
        load_python_agent(resolve_agent(tmp_path, "example"))


@pytest.mark.parametrize(
    "manifest",
    [None, {"entrypoint": "agent.py:custom_factory"}],
)
def test_missing_configured_factory(tmp_path, manifest):
    _write_agent(tmp_path, manifest=manifest, source="VALUE = 1\n")

    with pytest.raises(AgentFactoryError, match="does not expose a callable factory"):
        load_python_agent(resolve_agent(tmp_path, "example"))


def test_factory_exception_is_normalized(tmp_path):
    _write_agent(
        tmp_path,
        source="def create_agent():\n    raise LookupError('factory exploded')\n",
    )

    with pytest.raises(AgentFactoryError, match="LookupError: factory exploded"):
        load_python_agent(resolve_agent(tmp_path, "example"))


def test_invalid_factory_result_is_rejected(tmp_path):
    _write_agent(tmp_path, source="def create_agent():\n    return object()\n")

    with pytest.raises(AgentContractError) as caught:
        load_python_agent(resolve_agent(tmp_path, "example"))

    assert caught.value.code == "agent_contract_invalid"
    assert "reset, act" in str(caught.value)


@pytest.mark.parametrize("attribute", ["reset", "act"])
def test_noncallable_lifecycle_attribute_is_rejected(tmp_path, attribute):
    other = "act" if attribute == "reset" else "reset"
    _write_agent(
        tmp_path,
        source=f"""
class InvalidAgent:
    {attribute} = None

    def {other}(self, value):
        return None

def create_agent():
    return InvalidAgent()
""",
    )

    with pytest.raises(AgentContractError) as caught:
        load_python_agent(resolve_agent(tmp_path, "example"))

    assert caught.value.code == "agent_contract_invalid"
    assert f"missing callable {attribute}" in str(caught.value)


def test_same_source_filename_in_two_agents_does_not_collide(tmp_path):
    first_dir = _write_agent(tmp_path, "alpha", source=VALID_SOURCE + "\nMARKER = 'alpha'\n")
    second_dir = _write_agent(tmp_path, "beta", source=VALID_SOURCE + "\nMARKER = 'beta'\n")

    first = load_python_agent(resolve_agent(tmp_path, "alpha"))
    second = load_python_agent(resolve_agent(tmp_path, "beta"))

    assert first.source_path == first_dir / "agent.py"
    assert second.source_path == second_dir / "agent.py"
    assert first.instance.origin == str(first_dir / "agent.py")  # type: ignore[attr-defined]
    assert second.instance.origin == str(second_dir / "agent.py")  # type: ignore[attr-defined]
    assert type(first.instance).__module__ != type(second.instance).__module__


def test_existing_builtin_blob_and_legacy_python_discovery_remain_compatible(tmp_path):
    builtin = tmp_path / "agents" / "runner"
    builtin.mkdir(parents=True)
    (builtin / "agent.yaml").write_text('{"name":"runner","defaults":{}}')

    blob = tmp_path / "agents" / "custom_blob"
    blob.mkdir()
    (blob / "agent.yaml").write_text('{"name":"custom_blob"}')
    (blob / "model.blob").write_bytes(b"blob")

    legacy_python = tmp_path / "agents" / "legacy_python"
    legacy_python.mkdir()
    (legacy_python / "agent.py").write_text(VALID_SOURCE, encoding="utf-8")

    specs = discover_agents(tmp_path)

    assert specs["runner"].kind == "builtin"
    assert specs["runner"].defaults == {}
    assert specs["custom_blob"].kind == "blob"
    assert specs["custom_blob"].blob == blob / "model.blob"
    assert specs["legacy_python"].kind == "python"
    assert specs["legacy_python"].api_version is None
    assert specs["legacy_python"].entry_point == "agent.py:create_agent"
    with pytest.raises(UnsupportedAgentAPIVersionError):
        load_python_agent(specs["legacy_python"])
