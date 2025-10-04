# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.building.build_main import Analysis, PYZ
from PyInstaller.building.api import EXE, COLLECT

project_root = os.path.abspath(".")
engine_src   = os.path.join(project_root, "engine", "src")
assets_dir   = os.path.join(project_root, "assets")
script_path  = os.path.join(project_root, "app", "replay_viewer.py")  # ABSOLUTE

block_cipher = None
hiddenimports = collect_submodules("battle_engine")
datas = []
if os.path.isdir(assets_dir):
    datas.append((assets_dir, "assets"))

a = Analysis(
    [script_path],
    pathex=[project_root, engine_src],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=['PySide6.scripts.deploy', 'PySide6.scripts.deploy_lib', 'project_lib'],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas,
    name='battlereplayviewer',
    console=False,
    icon=None,
)
coll = COLLECT(exe, name='battlereplayviewer')
