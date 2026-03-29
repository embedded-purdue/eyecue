# backend.spec — PyInstaller spec for the EyeCue Flask backend
# Run from the repo root:  pyinstaller backend.spec

import sys
from pathlib import Path

ROOT = Path(SPECPATH)   # repo root (where this .spec lives)

a = Analysis(
    [str(ROOT / 'app' / '__main__.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # Include any non-.py assets from the app package if needed
    ],
    hiddenimports=[
        # Flask internals not always auto-discovered
        'flask',
        'flask_cors',
        'werkzeug',
        'jinja2',
        'click',
        'itsdangerous',
        'markupsafe',
        'blinker',
        # Project modules
        'app',
        'app.app',
        'app.config',
        'app.routes',
        'app.routes.app_state',
        'app.routes.runtime',
        'app.routes.serial',
        'app.services',
        'app.services.pipeline_controller',
        'app.services.contour_pupil_processor',
        'app.services.runtime_context',
        'app.serial_connect',
        'app.prefs_utils',
        # Optional runtime deps
        'pyserial',
        'serial',
        'serial.tools',
        'serial.tools.list_ports',
        'requests',
        'pyautogui',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='eyecue-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,        # UPX can cause issues on macOS; disable it
    console=True,     # Keep console=True so we can pipe stdout/stderr in Electron
    onefile=True,
)
