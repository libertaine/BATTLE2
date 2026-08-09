# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.building.build_main import Analysis, PYZ
from PyInstaller.building.api import EXE, COLLECT

# Invoke pyinstaller from repo root so "." is project root
project_root = os.path.abspath(".")
engine_src   = os.path.join(project_root, "engine", "src")
client_src   = os.path.join(project_root, "client", "src")
assets_dir   = os.path.join(project_root, "assets")
starter_agents_dir = os.path.join(engine_src, "battle_engine", "data", "starter_agents")
agent_template_dir = os.path.join(engine_src, "battle_engine", "data", "agent_template")
script_path  = os.path.join(project_root, "app", "agent_designer.py")  # ABSOLUTE

block_cipher = None
hiddenimports = collect_submodules("battle_engine") + collect_submodules("battle_client")
datas = []
if os.path.isdir(assets_dir):
    datas.append((assets_dir, "assets"))
if os.path.isdir(starter_agents_dir):
    datas.append((starter_agents_dir, "battle_engine/data/starter_agents"))
if os.path.isdir(agent_template_dir):
    datas.append((agent_template_dir, "battle_engine/data/agent_template"))

a = Analysis(
    [script_path],
    pathex=[project_root, engine_src, client_src],
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
    name='battle-agent-designer',
    console=False,
    icon=None,
)
coll = COLLECT(exe, name='battle-agent-designer')
