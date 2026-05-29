# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_data_files

datas = [
    ('assets', 'assets'),
    ('config', 'config'),
    ('manual_images', 'manual_images'),
    ('models', 'models'),
    ('screenshots', 'screenshots'),
    ('src', 'src'),
    ('用户手册.html', '.'),
    ('requirements.txt', '.'),
]
binaries = []
hiddenimports = [
    'transformers',
    'sentence_transformers',
    'huggingface_hub',
    'llama_index.core',
    'llama_index.core.node_parser',
    'llama_index.core.ingestion',
    'llama_index.embeddings.huggingface',
    'torch',
    'tiktoken',
    'tiktoken_ext',
    'tiktoken_ext.openai_public',
    'tokenizers',
    'numpy',
    'scipy',
    'sklearn',
    'PIL',
    'mss',
]

# PySide6 平台插件（避免打包后 Qt 平台无法加载）
datas += collect_data_files('PySide6')

# transformers / sentence_transformers / huggingface_hub / torch
for pkg in ('transformers', 'sentence_transformers', 'huggingface_hub', 'torch'):
    tmp_ret = collect_all(pkg)
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]

a = Analysis(
    ['src\\main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='FGO因陀罗桌宠',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\images\\icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='FGO因陀罗桌宠',
)
