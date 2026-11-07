"""Check local release assets; hashes detect corruption, not publisher identity."""
from __future__ import annotations
import hashlib
import json
import re
from pathlib import Path

MANIFEST = 'assets/offline_manifest.json'


def verify_assets(root):
    root=Path(root).resolve()
    failures=[]
    checked=0
    try:
        manifest_path=root/MANIFEST
        if manifest_path.stat().st_size>1_000_000:
            raise ValueError('Manifest exceeds size limit')
        data=json.loads(manifest_path.read_text(encoding='utf-8'))
        records=data['sha256']
        if not isinstance(records,dict) or not records or len(records)>10000:
            raise ValueError('Invalid checksum records')
        for name,expected in records.items():
            checked+=1
            if (not isinstance(name,str) or '\\' in name or ':' in name or
                Path(name).is_absolute() or '..' in Path(name).parts or
                not isinstance(expected,str) or not re.fullmatch('[0-9a-f]{64}',expected)):
                failures.append('Invalid manifest entry: '+str(name));continue
            path=root/name
            if not path.resolve().is_relative_to(root) or path.is_symlink():
                failures.append('Unsafe asset path: '+name);continue
            if not path.is_file():
                failures.append('Missing: '+name);continue
            try:
                digest=hashlib.sha256()
                with path.open('rb') as stream:
                    for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
                if digest.hexdigest()!=expected:failures.append('Checksum mismatch: '+name)
            except OSError as exc:failures.append(f'Unreadable: {name}: {exc}')
    except (OSError,ValueError,KeyError,TypeError) as exc:
        failures.append('Asset manifest unavailable or malformed: '+str(exc))
    return {'ok':not failures,'checked':checked,'failures':failures}
