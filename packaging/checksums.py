"""Produce plain SHA-256 checksums for release archives/installers."""
from pathlib import Path
import hashlib
import sys
root = Path(sys.argv[1])
files = sorted(p for p in root.iterdir() if p.is_file() and p.suffix in {'.zip', '.gz', '.rpm', '.exe'})
(root / 'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n' for p in files))
