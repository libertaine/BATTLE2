# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_submodules

project_root = os.path.abspath(".")
engine_src = os.path.join(project_root, "engine", "src")
client_src = os.path.join(project_root, "client", "src")
script_path = os.path.join(engine_src, "battle_engine", "__main__.py")
pmars_dir = os.path.join(project_root, "pmars", "windows")
icon_path = os.path.join(project_root, "assets", "branding", "bytefray-icon.ico")
branding_dir = os.path.join(project_root, "app", "assets", "branding")
starter_agents_dir = os.path.join(engine_src, "battle_engine", "data", "starter_agents")
agent_template_dir = os.path.join(engine_src, "battle_engine", "data", "agent_template")
agent_template_annotated_dir = os.path.join(
    engine_src, "battle_engine", "data", "agent_template_annotated"
)
pmars_datas = [
    (os.path.join(pmars_dir, "pmars.exe"), "pmars/windows"),
    (os.path.join(pmars_dir, "COPYING"), "pmars/windows"),
]
datas = list(pmars_datas)
if os.path.isdir(branding_dir):
    datas.append((branding_dir, "assets/branding"))
if os.path.isdir(starter_agents_dir):
    datas.append((starter_agents_dir, "battle_engine/data/starter_agents"))
if os.path.isdir(agent_template_dir):
    datas.append((agent_template_dir, "battle_engine/data/agent_template"))
if os.path.isdir(agent_template_annotated_dir):
    datas.append((agent_template_annotated_dir, "battle_engine/data/agent_template_annotated"))

hiddenimports = (
    collect_submodules("battle_engine")
    + collect_submodules("battle_client")
    + collect_submodules("app")
)

a = Analysis(
    [script_path],
    pathex=[project_root, engine_src, client_src],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="bytefray", console=True, icon=icon_path)
coll = COLLECT(exe, a.binaries, a.datas, name="bytefray")
