# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

hidden = collect_submodules('PySide6') + collect_submodules('battle_engine') + collect_submodules('battle_client')
datas = []
datas += collect_data_files('agents', includes=['agents/**'])
datas += collect_data_files('assets', includes=['assets/**'])

exe = EXE(
    PYZ([]),
    script='app\\main.py',
    pathex=['.', 'engine\\src', 'client\\src'],
    hiddenimports=hidden,
    datas=datas,
    console=False,
    name='BattleAgentDesigner',
)
coll = COLLECT(exe, strip=False, upx=False, name='BattleAgentDesigner')
