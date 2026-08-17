# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_submodules

project_root = os.path.abspath(".")
engine_src = os.path.join(project_root, "engine", "src")
script_path = os.path.join(engine_src, "battle_engine", "cli.py")
pmars_dir = os.path.join(project_root, "pmars", "windows")
icon_path = os.path.join(project_root, "assets", "branding", "bytefray-icon.ico")
starter_agents_dir = os.path.join(engine_src, "battle_engine", "data", "starter_agents")
pmars_datas = [
    (os.path.join(pmars_dir, "pmars.exe"), "pmars/windows"),
    (os.path.join(pmars_dir, "COPYING"), "pmars/windows"),
]
datas = list(pmars_datas)
if os.path.isdir(starter_agents_dir):
    datas.append((starter_agents_dir, "battle_engine/data/starter_agents"))

a = Analysis(
    [script_path],
    pathex=[project_root, engine_src],
    binaries=[],
    datas=datas,
    hiddenimports=collect_submodules("battle_engine"),
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="bytefray-cli", console=True, icon=icon_path)
coll = COLLECT(exe, a.binaries, a.datas, name="bytefray-cli")
