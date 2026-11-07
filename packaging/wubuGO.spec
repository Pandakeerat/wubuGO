# Run from repository root: pyinstaller --clean --noconfirm packaging/wubuGO.spec
from pathlib import Path
import sys
root = Path(SPECPATH).parent
assets = [(str(root / name), name) for name in ('assets', 'data', 'templates', 'docs')]
assets += [(str(root / name), '.') for name in ('LICENSE', 'README.md', 'QUICK_START.txt')]
a = Analysis([str(root / 'wubuGO.pyw')], pathex=[str(root)], binaries=[], datas=assets,
             hiddenimports=['tkinter', 'tkinter.ttk', 'tkinter.filedialog', 'tkinter.messagebox'],
             hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='wubuGO', debug=False,
          bootloader_ignore_signals=False, strip=False, upx=False, console=False,
          icon=str(root / 'assets/logo.ico') if sys.platform == 'win32' else None)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='wubuGO')
