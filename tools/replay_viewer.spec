# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

hidden = collect_submodules('pygame') + collect_submodules('battle_client')
datas = collect_data_files('assets', includes=['assets/**'])

exe = EXE(
    PYZ([]),
    script='client\\src\\battle_client\\cli.py',
    pathex=['.', 'client\\src', 'engine\\src'],
    hiddenimports=hidden,
    datas=datas,
    console=True,
    name='BattleReplayViewer',
)
coll = COLLECT(exe, strip=False, upx=False, name='BattleReplayViewer')
