"""Copy installed runtime notices and record unresolved coverage; never claim legal clearance.
Run with the build Python: python packaging/collect_licenses.py dist/wubuGO
"""
from __future__ import annotations
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import sysconfig


def command(args):
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=15)
        return result.stdout.strip() if result.returncode == 0 else ''
    except (OSError, subprocess.TimeoutExpired):
        return ''


def collect(bundle):
    bundle = Path(bundle).resolve()
    if not bundle.is_dir():
        raise ValueError('Frozen application directory does not exist')
    dest = bundle/'THIRD-PARTY-LICENSES'
    dest.mkdir(exist_ok=True)
    notices, missing, components = [], [], []
    seen = {}
    def group(name, paths, version=None):
        found = False
        for source in paths:
            source = Path(source)
            if not source.is_file():
                continue
            blob = source.read_bytes()
            digest = hashlib.sha256(blob).hexdigest()
            if digest not in seen:
                safe = re.sub(r'[^A-Za-z0-9._-]+', '_', name)
                target = dest/(safe+'-'+digest[:10]+'-'+source.name)
                target.write_bytes(blob)
                seen[digest] = target.name
            notices.append({'component':name,'source':str(source),'file':seen[digest],'sha256':digest})
            found = True
        components.append({'name':name,'version':version,'notices_found':found})
        if not found:
            missing.append({'component':name,'reason':'No installed license text found in known locations'})
        return found
    prefix = Path(sys.base_prefix)
    ver = f'{sys.version_info.major}.{sys.version_info.minor}'
    python_notices = [prefix/'LICENSE.txt',prefix/'LICENSE',
          Path('/usr/share/doc')/('python'+ver)/'copyright',
          Path('/usr/share/doc')/('libpython'+ver+'-stdlib')/'copyright']
    for name in ('python3','python3-libs','python'+ver):
        python_notices += list((Path('/usr/share/licenses')/name).glob('*'))
    group('Python',python_notices,sys.version)
    for name in ('pyinstaller','pyinstaller-hooks-contrib','altgraph'):
        try:
            package = metadata.distribution(name)
            paths = [package.locate_file(p) for p in package.files or []
                     if any(part.lower().startswith(('license','copying')) for part in p.parts)]
            group(name,paths,package.version)
        except metadata.PackageNotFoundError:
            missing.append({'component':name,'reason':'Build distribution metadata unavailable'})
    for name, names in [('Tcl',('tcl','tcl8.6','libtcl8.6','tcl9.0','libtcl9.0')),
                        ('Tk',('tk','tk8.6','libtk8.6','tk9.0','libtk9.0'))]:
        paths = [Path('/usr/share/doc')/n/'copyright' for n in names]
        for base in (prefix/'tcl',prefix/'lib',Path('/usr/share/tcltk')):
            if base.is_dir():
                paths += list(base.glob(name.lower()+'*/license*'))
                paths += list(base.glob(name.lower()+'*/LICENSE*'))
        for n in names:
            paths += list((Path('/usr/share/licenses')/n).glob('*'))
        group(name,paths)
    native = sorted(p for p in bundle.rglob('*') if p.is_file() and
                    (p.name.endswith('.so') or '.so.' in p.name or p.suffix.lower() in {'.dll','.pyd','.dylib'}))
    debian, rpm = bool(shutil.which('dpkg-query')), bool(shutil.which('rpm'))
    cache, visited = {}, set()
    for binary in native:
        name = binary.name
        if name in visited:
            continue
        visited.add(name)
        packages = set()
        if debian:
            for line in command(['dpkg-query','-S','*/'+name]).splitlines():
                if ': ' in line:
                    packages.update(line.split(': ',1)[0].split(', '))
        elif rpm:
            for path in (prefix/'lib64'/name,prefix/'lib'/name,
                         Path(sysconfig.get_config_var('DESTSHARED') or '')/name):
                if path.exists():
                    packages.update(command(['rpm','-qf',str(path),'--qf','%{NAME}\n']).splitlines())
            if not packages:
                packages.update(command(['rpm','-q','--whatprovides',name+'()(64bit)',
                                         '--qf','%{NAME}\n']).splitlines())
        elif os.name == 'nt':
            components.append({'name':name,'notice_reference':'Python LICENSE.txt; review DLL coverage individually'})
            continue
        if not packages:
            missing.append({'component':str(binary.relative_to(bundle)),
                            'reason':'Installed package owning bundled native binary not found'})
        for package in sorted(packages):
            if package not in cache:
                if debian:
                    plain = package.split(':')[0]
                    paths = [Path('/usr/share/doc')/package/'copyright',Path('/usr/share/doc')/plain/'copyright']
                    version = command(['dpkg-query','-W','-f=${Version}',package])
                else:
                    paths = [Path(p) for p in command(['rpm','-ql',package]).splitlines() if '/usr/share/licenses/' in p]
                    version = command(['rpm','-q',package,'--qf','%{VERSION}-%{RELEASE}'])
                cache[package] = group(package,paths,version)
            components.append({'name':str(binary.relative_to(bundle)),
                               'installed_package':package,'notices_found':cache[package]})
    report = {'build_python':sys.version,'build_platform':sys.platform,'components':components,
              'notices':notices,'missing':missing,'complete_legal_review':False,
              'scope':'Installed runtime/package license texts collected without modification. '
                      'A found text does not establish redistribution rights. Review unresolved entries '
                      'and all applicable terms before public release.'}
    (dest/'manifest.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    (dest/'README.txt').write_text(report['scope']+'\n',encoding='utf-8')
    print(f'Collected {len(seen)} distinct notice files; {len(missing)} unresolved entries. See {dest}/manifest.json')
    return report

if __name__ == '__main__':
    collect(sys.argv[1])
