# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['filter_app.py'],
    pathex=[],
    binaries=[('fastfilter.dll', '.')],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'unittest',
        'pydoc',
        'pydoc_data',
        'xmlrpc',
        'ftplib',
        'tarfile',
        'test',
        'distutils',
        'email',
        'http.server',
        'sqlite3',
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Wordlist-Edit-Tool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
