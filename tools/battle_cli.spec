# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_submodules

project_root = os.path.abspath(".")
engine_src = os.path.join(project_root, "engine", "src")
script_path = os.path.join(engine_src, "battle_engine", "cli.py")
pmars_dir = os.path.join(project_root, "pmars", "windows")
pmars_datas = [
    (os.path.join(pmars_dir, "pmars.exe"), "pmars/windows"),
    (os.path.join(pmars_dir, "COPYING"), "pmars/windows"),
]

a = Analysis(
    [script_path],
    pathex=[project_root, engine_src],
    binaries=[],
    datas=pmars_datas,
    hiddenimports=collect_submodules("battle_engine"),
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="battle-cli", console=True)
coll = COLLECT(exe, a.binaries, a.datas, name="battle-cli")
