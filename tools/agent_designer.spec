# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.building.datastruct import Tree
import os

hidden = (
    collect_submodules('PySide6') +
    collect_submodules('battle_engine') +
    collect_submodules('battle_client')
)

datas = []
for p, pref in (('..\\assets','assets'), ('..\\agents','agents')):
    if os.path.isdir(p):
        datas.append(Tree(p, prefix=pref))

a = Analysis(
    [...],
    pathex=['..', '..\\client\\src', '..\\engine\\src'],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)   # MUST be here
exe = EXE(
    a.scripts,
    exclude_binaries=True,
    name='BattleAgentDesigner',
    console=True
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='BattleAgentDesigner'
)
