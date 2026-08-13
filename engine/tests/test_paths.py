from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from battle_engine import cli, paths

from app.services import osutil


@pytest.fixture(autouse=True)
def clear_root_environment(monkeypatch):
    monkeypatch.delenv("BYTEFRAY_ROOT", raising=False)
    monkeypatch.delenv("BATTLE2_ROOT", raising=False)
    monkeypatch.delenv("BATTLE_ROOT", raising=False)


def test_bytefray_root_precedes_both_legacy_roots(monkeypatch, tmp_path):
    preferred = tmp_path / "preferred root"
    legacy_v2 = tmp_path / "legacy v2 root"
    legacy_v1 = tmp_path / "legacy v1 root"
    monkeypatch.setenv("BYTEFRAY_ROOT", str(preferred))
    monkeypatch.setenv("BATTLE2_ROOT", str(legacy_v2))
    monkeypatch.setenv("BATTLE_ROOT", str(legacy_v1))

    assert paths.get_data_root() == preferred.resolve()
    assert cli._battle_root() == preferred.resolve()
    assert osutil.get_battle_root() == preferred.resolve()


def test_battle2_root_precedes_legacy_root_when_bytefray_root_is_empty(monkeypatch, tmp_path):
    preferred = tmp_path / "preferred root"
    legacy = tmp_path / "legacy root"
    monkeypatch.setenv("BYTEFRAY_ROOT", "   ")
    monkeypatch.setenv("BATTLE2_ROOT", str(preferred))
    monkeypatch.setenv("BATTLE_ROOT", str(legacy))

    assert paths.get_data_root() == preferred.resolve()
    assert cli._battle_root() == preferred.resolve()
    assert osutil.get_battle_root() == preferred.resolve()


def test_legacy_root_is_fallback_when_bytefray_and_battle2_root_are_empty(monkeypatch, tmp_path):
    legacy = tmp_path / "legacy data"
    monkeypatch.setenv("BYTEFRAY_ROOT", "")
    monkeypatch.setenv("BATTLE2_ROOT", "   ")
    monkeypatch.setenv("BATTLE_ROOT", str(legacy))

    assert paths.get_data_root() == legacy.resolve()


def test_empty_configured_roots_are_ignored(monkeypatch):
    monkeypatch.setenv("BYTEFRAY_ROOT", "")
    monkeypatch.setenv("BATTLE2_ROOT", "")
    monkeypatch.setenv("BATTLE_ROOT", "  ")

    assert paths.configured_data_root() is None
    assert paths.get_data_root().is_absolute()


def test_relative_configured_root_is_absolute_and_preserves_spaces(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BYTEFRAY_ROOT", os.path.join("relative parent", "data files"))

    resolved = paths.get_data_root()

    assert resolved == (tmp_path / "relative parent" / "data files").resolve()
    assert "data files" in str(resolved)


def test_meipass_is_resource_only_and_executable_parent_is_writable_root(
    monkeypatch, tmp_path
):
    extraction = tmp_path / "temporary extraction"
    executable = tmp_path / "portable app" / "battle2.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(extraction), raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))

    assert paths.get_resource_root() == extraction.resolve()
    assert paths.get_data_root() == executable.parent.resolve()
    assert paths.get_data_root() != paths.get_resource_root()


def test_explicit_data_root_wins_in_frozen_application(monkeypatch, tmp_path):
    configured = tmp_path / "installed data"
    extraction = tmp_path / "temporary extraction"
    monkeypatch.setenv("BATTLE2_ROOT", str(configured))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(extraction), raising=False)

    assert paths.get_data_root() == configured.resolve()
    assert paths.get_resource_root() == extraction.resolve()


def test_source_checkout_defaults_remain_repository_compatible():
    repository = Path(__file__).resolve().parents[2]

    assert paths.get_data_root() == repository
    assert paths.get_resource_root() == repository


def test_source_checkout_detection_matches_expected_source_layout(monkeypatch, tmp_path):
    repository = tmp_path / "repo"
    module_path = repository / "engine" / "src" / "battle_engine" / "paths.py"
    module_path.parent.mkdir(parents=True)
    module_path.write_text("# stand-in for the real source file\n")
    (repository / "client").mkdir()
    monkeypatch.setattr(paths, "__file__", str(module_path))

    assert paths._source_checkout_root() == repository.resolve()


def test_source_checkout_detection_ignores_unrelated_ancestor_checkout(monkeypatch, tmp_path):
    """Regression: installing the built wheel into a venv nested under this
    repository's own checkout previously redirected the writable data root
    to the repository's ``agents/`` directory instead of the documented
    installed-platform default, because the old detection walked every
    ancestor directory looking for sibling engine/+client/ folders rather
    than checking this module's own known source-tree position.
    """
    unrelated_checkout = tmp_path / "unrelated checkout"
    (unrelated_checkout / "engine").mkdir(parents=True)
    (unrelated_checkout / "client").mkdir()
    installed_module = (
        unrelated_checkout
        / ".venv"
        / "lib"
        / "python3.12"
        / "site-packages"
        / "battle_engine"
        / "paths.py"
    )
    installed_module.parent.mkdir(parents=True)
    installed_module.write_text("# stand-in for an installed (non-editable) copy\n")
    monkeypatch.setattr(paths, "__file__", str(installed_module))

    assert paths._source_checkout_root() is None


def test_regular_install_uses_package_container_for_resources(monkeypatch):
    monkeypatch.setattr(paths, "_source_checkout_root", lambda: None)

    assert paths.get_resource_root() == Path(paths.__file__).resolve().parent.parent


def test_installed_linux_uses_xdg_data_home(monkeypatch, tmp_path):
    working = tmp_path / "working directory"
    xdg_data = tmp_path / "xdg data"
    working.mkdir()
    monkeypatch.chdir(working)
    monkeypatch.setattr(paths, "_source_checkout_root", lambda: None)
    resolved = paths.installed_data_root(
        {"XDG_DATA_HOME": str(xdg_data), "HOME": str(tmp_path / "unused home")},
        platform="linux",
    )

    assert resolved == (xdg_data / "battle2").resolve()
    assert resolved != working.resolve()


def test_installed_linux_defaults_under_isolated_home(monkeypatch, tmp_path):
    home = tmp_path / "isolated home"
    resolved = paths.installed_data_root({"HOME": str(home)}, platform="linux")

    assert resolved == (home / ".local" / "share" / "battle2").resolve()


def test_source_checkout_ignores_xdg_default(monkeypatch, tmp_path):
    repository = tmp_path / "source checkout"
    monkeypatch.setattr(paths, "_source_checkout_root", lambda: repository)
    monkeypatch.setattr(sys, "platform", "linux")

    assert paths.get_data_root({"XDG_DATA_HOME": str(tmp_path / "xdg")}) == repository


@pytest.mark.skipif(sys.platform != "win32", reason="Windows installed-wheel policy")
def test_regular_windows_install_uses_local_app_data(monkeypatch, tmp_path):
    working = tmp_path / "windows working directory"
    local_app_data = tmp_path / "local application data"
    working.mkdir()
    monkeypatch.chdir(working)
    monkeypatch.setattr(paths, "_source_checkout_root", lambda: None)

    resolved = paths.get_data_root(
        {"LOCALAPPDATA": str(local_app_data), "XDG_DATA_HOME": str(tmp_path / "ignored")}
    )

    assert resolved == (local_app_data / "BATTLE2").resolve()
    assert resolved != working.resolve()


def test_regular_windows_install_falls_back_under_user_profile(tmp_path):
    profile = tmp_path / "user profile"

    resolved = paths.installed_data_root({"USERPROFILE": str(profile)}, platform="win32")

    assert resolved == (profile / "AppData" / "Local" / "BATTLE2").resolve()


def test_branding_icon_resolves_in_source_checkout():
    repository = Path(__file__).resolve().parents[2]

    resolved = paths.get_branding_icon_path()

    assert resolved == repository / "assets" / "branding" / "bytefray-icon.png"
    assert resolved.is_file()


def test_branding_icon_resolves_under_frozen_meipass(monkeypatch, tmp_path):
    extraction = tmp_path / "temporary extraction"
    (extraction / "assets" / "branding").mkdir(parents=True)
    icon = extraction / "assets" / "branding" / "bytefray-icon.png"
    icon.write_bytes(b"stand-in icon bytes")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(extraction), raising=False)

    assert paths.get_branding_icon_path() == icon.resolve()


def test_branding_icon_falls_back_to_app_assets_for_wheel_installs(monkeypatch, tmp_path):
    package_container = tmp_path / "site-packages"
    (package_container / "app" / "assets" / "branding").mkdir(parents=True)
    icon = package_container / "app" / "assets" / "branding" / "bytefray-icon.png"
    icon.write_bytes(b"stand-in icon bytes")
    monkeypatch.setattr(paths, "get_resource_root", lambda: package_container)

    assert paths.get_branding_icon_path() == icon.resolve()


def test_branding_icon_returns_none_when_unresolvable(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "get_resource_root", lambda: tmp_path / "empty")

    assert paths.get_branding_icon_path() is None


def test_default_paths_normalize_their_writable_root(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    defaults = osutil.get_default_paths(Path("data root"))

    assert defaults.root == (tmp_path / "data root").resolve()
    assert defaults.replay_path == defaults.root / "runs" / "_loose" / "replay.jsonl"
    assert defaults.summary_path == defaults.root / "runs" / "_loose" / "summary.json"
